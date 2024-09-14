import re
import time
from typing import Dict, List, Tuple, Optional

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from flask import Flask, request, render_template
from urllib.parse import urljoin

app = Flask(__name__)

def fetch_page(url: str) -> BeautifulSoup:
    """Fetch and parse the HTML content of a given URL."""
    response = requests.get(url)
    return BeautifulSoup(response.text, 'html.parser')

def find_main_content(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    """Find the main content area of the page, excluding navigation and sidebar content."""
    for element in soup.find_all(['nav', 'header', 'footer', 'aside']):
        element.decompose()

    main_content = (
        soup.find('div', class_=lambda x: x and any(c in x for c in ['content', 'main', 'article', 'post']))
        or soup.find('article')
        or soup.find('main')
    )

    if not main_content:
        return None

    for ul in main_content.find_all('ul'):
        if all(li.find('a') for li in ul.find_all('li')):
            ul.decompose()

    return main_content

def extract_text_content(tag: BeautifulSoup, blockquote_text: set) -> Optional[Dict]:
    """Extract text content from a tag, considering blockquotes."""
    text = tag.get_text(strip=True)
    if text and text not in blockquote_text:
        return {'tag': tag.name, 'text': text}
    return None

def extract_link_content(tag: BeautifulSoup, blockquote_text: set, base_url: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Extract link content from a tag, considering blockquotes and handling relative URLs."""
    text = tag.get_text(strip=True)
    ignored_terms = ['sign up', 'sign in', 'follow', 'login', 'register', 'subscribe']
    
    if text.lower() not in blockquote_text and not any(term in text.lower() for term in ignored_terms):
        href = tag.get('href')
        if href:
            href = urljoin(base_url, href)
        content = {'tag': 'a', 'text': text, 'href': href}
        link = {'text': text, 'href': href}
        return content, link
    return None, None

def extract_strong_content(tag: BeautifulSoup, blockquote_text: set) -> Optional[Dict]:
    """Extract strong content from a tag, considering blockquotes."""
    text = tag.get_text(strip=True)
    if text not in blockquote_text:
        return {'tag': 'strong', 'text': text}
    return None

def extract_pre_content(tag: BeautifulSoup) -> Dict:
    """Extract pre-formatted content from a tag."""
    pre_content = []
    for child in tag.children:
        if isinstance(child, str):
            pre_content.append({'tag': None, 'text': child.rstrip('\n')})
        elif child.name == 'span':
            span_content = [
                {'tag': None, 'text': span_child.rstrip('\n')} if isinstance(span_child, str) else
                {'tag': 'br', 'text': ''} if span_child.name == 'br' else
                {'tag': span_child.name, 'text': span_child.get_text(strip=False).rstrip('\n')}
                for span_child in child.children
            ]
            pre_content.append({'tag': 'span', 'content': span_content})
        elif child.name == 'br':
            pre_content.append({'tag': 'br', 'text': ''})
        else:
            pre_content.append({'tag': child.name, 'text': child.get_text(strip=False).rstrip('\n')})
    return {'tag': 'pre', 'text': pre_content}

def extract_list_content(tag: BeautifulSoup, blockquote_text: set) -> Optional[Dict]:
    """Extract list content from a tag, considering blockquotes."""
    list_items = [li.get_text(strip=True) for li in tag.find_all('li', recursive=False)
                  if li.get_text(strip=True) and li.get_text(strip=True) not in blockquote_text and not li.find('a')]
    if list_items:
        return {'tag': tag.name, 'text': list_items}
    return None


def extract_blockquote_content(tag: BeautifulSoup, blockquote_text: set, base_url: str) -> Tuple[Optional[Dict], List[Dict]]:
    """Extract blockquote content from a tag."""
    blockquote_content = []
    links = []
    for child in tag.children:
        if child.name == 'p':
            p_content, p_links = extract_paragraph_content(child, blockquote_text, base_url, is_blockquote=True)
            if p_content:
                blockquote_content.append(p_content)
            links.extend(p_links)
        elif child.name == 'strong':
            strong_content = extract_strong_content(child, blockquote_text)
            if strong_content:
                blockquote_content.append(strong_content)
                blockquote_text.add(strong_content['text'])
    if blockquote_content:
        return {'tag': 'blockquote', 'text': blockquote_content}, links
    return None, links

def extract_paragraph_content(tag: BeautifulSoup, blockquote_text: set, base_url: str, is_blockquote: bool = False) -> Tuple[Optional[Dict], List[Dict]]:
    """Extract paragraph content from a tag."""
    p_content = []
    links = []
    for child in tag.children:
        if isinstance(child, str):
            text_content = extract_text_content(child, blockquote_text)
            if text_content:
                p_content.append(text_content)
                if is_blockquote:
                    blockquote_text.add(text_content['text'])
        elif child.name == 'a':
            link_content, link = extract_link_content(child, blockquote_text, base_url)
            if link_content:
                p_content.append(link_content)
                links.append(link)
                if is_blockquote:
                    blockquote_text.add(link_content['text'])
        elif child.name == 'strong':
            strong_content = extract_strong_content(child, blockquote_text)
            if strong_content:
                p_content.append(strong_content)
                if is_blockquote:
                    blockquote_text.add(strong_content['text'])
    if p_content:
        return {'tag': 'p', 'text': p_content}, links
    return None, links

def extract_content(soup: BeautifulSoup, base_url: str) -> Tuple[List[Dict], List[Dict]]:
    """Extract content from the BeautifulSoup object."""
    content = []
    links = []
    blockquote_text = set()
    main_content = find_main_content(soup)
    
    for tag in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'pre', 'ul', 'ol', 'blockquote']):
        if tag.name == 'blockquote':
            blockquote_content, blockquote_links = extract_blockquote_content(tag, blockquote_text, base_url)
            if blockquote_content:
                content.append(blockquote_content)
            links.extend(blockquote_links)
        elif tag.name.startswith('h'):
            heading_content = extract_text_content(tag, blockquote_text)
            if heading_content:
                content.append(heading_content)
        elif tag.name == 'p':
            p_content, p_links = extract_paragraph_content(tag, blockquote_text, base_url)
            if p_content:
                content.append(p_content)
            links.extend(p_links)
        elif tag.name == 'pre':
            content.append(extract_pre_content(tag))
        elif tag.name in ['ul', 'ol']:
            list_content = extract_list_content(tag, blockquote_text)
            if list_content:
                content.append(list_content)
    
    return content, links

def classify_content(url: str, content: str) -> str:
    """Classify the content type based on URL and content."""
    if "recipe" in url or "recipe" in content.lower():
        return "Recipe"
    elif "product" in url or "buy" in url:
        return "Product Page"
    else:
        return "Article"

def extract_date(soup: BeautifulSoup) -> Optional[str]:
    """Extract the publication date from the BeautifulSoup object."""
    text = soup.get_text()
    date_patterns = [
        r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b',
        r'\d{4}-\d{2}-\d{2}',
        r'\d{2}/\d{2}/\d{4}',
    ]
    
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            date_str = match.group()
            if re.match(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', date_str):
                return date_str
            try:
                return date_parser.parse(date_str).strftime("%b %d, %Y")
            except ValueError:
                return date_str
    return None

def extract_author(soup: BeautifulSoup) -> Optional[Dict]:
    """Extract the author information from the BeautifulSoup object."""
    author_meta = soup.find('meta', attrs={'name': 'author'})
    author_url_meta = soup.find('meta', attrs={'property': 'article:author'})
    
    if author_meta and author_url_meta:
        return {'name': author_meta['content'], 'url': author_url_meta['content']}
    elif author_meta:
        return {'name': author_meta['content']}
    elif author_url_meta:
        return {'url': author_url_meta['content']}
    return None

def extract_metadata(soup: BeautifulSoup) -> Dict:
    """Extract metadata from the BeautifulSoup object."""
    return {
        'publication_date': extract_date(soup),
        'author': extract_author(soup)
    }

def parse_url(url: str, depth: int = 1) -> Dict:
    """Parse the given URL and extract content, metadata, and links."""
    try:
        soup = fetch_page(url)
        base_url = '/'.join(url.split('/')[:3])
        content_text, additional_links = extract_content(soup, base_url)
        
        if not content_text:
            return {"error": "No content could be extracted from this page"}
        
        content_type = classify_content(url, ' '.join([item['text'] for item in content_text if isinstance(item['text'], str)]))
        metadata = extract_metadata(soup)
        
        ignored_terms = ['sign up', 'sign in', 'follow', 'login', 'register', 'subscribe', 'open in app']
        all_links = soup.find_all('a', href=True)
        filtered_links = []
        for a in all_links:
            link_text = a.get_text(strip=True)
            href = a.get('href')
            if link_text and href and not any(term in link_text.lower() for term in ignored_terms):
                full_url = urljoin(base_url, href)
                filtered_links.append({'text': link_text, 'href': full_url})
        
        for link in additional_links:
            if link['text'] and link['href'] and not any(term in link['text'].lower() for term in ignored_terms):
                filtered_links.append(link)
        
        unique_links = []
        seen = set()
        for link in filtered_links:
            if link['href'] not in seen:
                unique_links.append(link)
                seen.add(link['href'])
        
        result = {
            "content": content_text,
            "type": content_type,
            "metadata": metadata,
            "links": unique_links[:10]
        }
        
        return result
    except Exception as e:
        return {"error": f"An error occurred while parsing the URL: {str(e)}"}

@app.route('/', methods=['GET', 'POST'])
def index():
    """Handle the index route for both GET and POST requests."""
    if request.method == 'POST':
        url = request.form.get('url')
        
        if not url:
            return render_template('index.html', error="URL is required")
        
        result = parse_url(url)
        return render_template('index.html', result=result)
    
    return render_template('index.html')

if __name__ == "__main__":
    app.run(debug=True, port=5000)