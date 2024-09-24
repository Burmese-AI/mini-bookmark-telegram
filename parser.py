import json
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser
from flask import Flask, jsonify, render_template, request
from ratelimit import limits, sleep_and_retry

app = Flask(__name__)

RATE_LIMIT = 5
CALLS = 1
SAVES_FILE = '/tmp/saves.json'

@sleep_and_retry
@limits(calls=CALLS, period=RATE_LIMIT)
def fetch_page(url: str) -> Optional[BeautifulSoup]:
    """
    Fetch and parse a web page with rate limiting.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser')
    except requests.exceptions.RequestException:
        return None

def find_main_content(soup: BeautifulSoup) -> Optional[BeautifulSoup]:
    """
    Identify and extract the main content from a parsed web page.
    """
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

# Content extraction functions
def extract_content(main_content: BeautifulSoup) -> List[Dict]:
    """Extract content from the main content area."""
    content = []
    for tag in main_content.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'pre', 'strong']):
        if tag.name == 'blockquote':
            blockquote_content = extract_blockquote_content(tag)
            if blockquote_content:
                content.append(blockquote_content)
        elif tag.name == 'pre':
            content.append(extract_pre_content(tag))
        elif tag.name == 'strong':
            content.append({'tag': 'strong', 'text': tag.get_text(strip=True)})
        else:
            text = tag.get_text(strip=True)
            if text:
                content.append({'tag': tag.name, 'text': text})

    content = filter_empty_headings(content)

    return content

def extract_text_content(tag: BeautifulSoup, blockquote_text: set) -> Optional[Dict]:
    """Extract text content from a BeautifulSoup tag."""
    text = tag.get_text(strip=True)
    return {'tag': tag.name, 'text': text} if text and text not in blockquote_text else None

def extract_link_content(tag: BeautifulSoup, blockquote_text: set, base_url: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    """Extract link content from a BeautifulSoup tag."""
    text = tag.get_text(strip=True)
    href = urljoin(base_url, tag.get('href', ''))
    ignored_terms = [
        'sign up', 'sign in', 'follow', 'login', 'register', 'subscribe',
        'next', 'previous', 'older', 'newer', 'back', 'forward',
        'first', 'last', 'page', 'comment', 'reply', 'edit',
        '« previous', 'next »', '<<', '>>', '«', '»',
        'terms', 'privacy', 'cookie', 'about us', 'contact',
        'rss', 'feed', 'archive', 'category', 'tag'
    ]

    if (text.lower() not in blockquote_text and
        not any(term in text.lower() for term in ignored_terms) and
        not text.strip().isdigit() and
        href.startswith('http') and
        len(text.strip()) > 1 and
        not re.match(r'^(\d+|(\d+\s+comments?))$', text.strip(), re.IGNORECASE)):
        return {'tag': 'a', 'text': text, 'href': href}, {'text': text, 'href': href}
    return None, None

def extract_strong_content(tag: BeautifulSoup, blockquote_text: set) -> Optional[Dict]:
    """Extract strong content from a BeautifulSoup tag."""
    text = tag.get_text(strip=True)
    return {'tag': 'strong', 'text': text} if text not in blockquote_text else None

def extract_pre_content(tag: BeautifulSoup) -> Dict:
    """Extract pre content from a BeautifulSoup tag."""
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
    """Extract list content from a BeautifulSoup tag."""
    list_items = [li.get_text(strip=True) for li in tag.find_all('li', recursive=False)
                  if li.get_text(strip=True) and li.get_text(strip=True) not in blockquote_text and not li.find('a')]
    return {'tag': tag.name, 'text': list_items} if list_items else None

def extract_blockquote_content(tag: BeautifulSoup, blockquote_text: set, base_url: str) -> Tuple[Optional[Dict], List[Dict]]:
    """Extract blockquote content from a BeautifulSoup tag."""
    blockquote_content = []
    blockquote_text = set()
    base_url = ''

    for child in tag.children:
        if child.name == 'p':
            p_content, _ = extract_paragraph_content(child, blockquote_text, base_url, is_blockquote=True)
            if p_content:
                blockquote_content.append(p_content)
        elif child.name == 'strong':
            strong_content = extract_strong_content(child, blockquote_text)
            if strong_content:
                blockquote_content.append(strong_content)
                blockquote_text.add(strong_content['text'])

    return {'tag': 'blockquote', 'text': blockquote_content} if blockquote_content else None

def extract_paragraph_content(tag: BeautifulSoup, blockquote_text: set, base_url: str, is_blockquote: bool = False) -> Tuple[Optional[Dict], List[Dict]]:
    """Extract paragraph content from a BeautifulSoup tag."""
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
    return ({'tag': 'p', 'text': p_content}, links) if p_content else (None, links)

def extract_links(soup: BeautifulSoup, base_url: str) -> List[Dict]:
    """Extract links from the soup object."""
    links = []
    ignored_terms = [
        'previous', 'next', 'older', 'newer', '«', '»',
        'first', 'last', 'page', 'comment', 'reply'
    ]
    for a_tag in soup.find_all('a', href=True):
        href = urljoin(base_url, a_tag['href'])
        text = a_tag.get_text(strip=True)

        # Check if the link text contains version numbers or dates
        if re.search(r'\b\d+\.\d+(\.\d+)?\b', text) or re.search(r'\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2},?\s+\d{4}\b', text):
            continue

        if (href.startswith('http') and text and
            not any(term in text.lower() for term in ignored_terms) and
            not text.strip().isdigit() and
            not re.match(r'^(\d+|(\d+\s+comments?))$', text.strip(), re.IGNORECASE)):
            links.append({'text': text, 'href': href})
    return links

def filter_empty_headings(content: List[Dict]) -> List[Dict]:
    """Remove empty headings from the content."""
    filtered_content = []
    for i, item in enumerate(content):
        if item['tag'].startswith('h'):
            if i == len(content) - 1 or content[i+1]['tag'].startswith('h'):
                continue
        filtered_content.append(item)
    return filtered_content

def find_next_page(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Find the URL of the next page, if it exists."""
    next_link = soup.find('a', text=re.compile(r'next|older|»', re.I))
    if next_link and 'href' in next_link.attrs:
        return urljoin(base_url, next_link['href'])

    page_links = soup.find_all('a', href=re.compile(r'\?page=\d+'))
    if page_links:
        current_page = int(re.search(r'\?page=(\d+)', soup.url).group(1)) if '?page=' in soup.url else 1
        next_page_link = next((link for link in page_links if int(re.search(r'\?page=(\d+)', link['href']).group(1)) == current_page + 1), None)
        if next_page_link:
            return urljoin(base_url, next_page_link['href'])

    return None

# Content classification function
def classify_content(url: str, content: str, metadata: dict) -> str:
    """
    Classify the type of content based on URL, content, and metadata.
    """
    domain = urlparse(url).netloc.lower()
    path = urlparse(url).path.lower()
    lower_content = content.lower()[:1000]

    patterns = {
        "News": (r'\b(breaking news|latest update|press release)\b', ['news', 'bbc', 'cnn', 'nytimes', 'reuters', 'ap']),
        "Recipe": (r'\b(ingredients|directions|prep time|cook time)\b', ['recipe', 'food', 'cooking']),
        "Product": (r'\b(add to cart|product details|shipping info)\b', ['product', 'shop', 'store']),
        "Review": (r'\b(review|rating|stars out of|verdict)\b', ['review']),
        "Tutorial": (r'\b(step [1-9]|how to|tutorial|guide)\b', ['tutorial', 'how-to']),
        "Blog Post": (r'\b(posted on|blog post|thoughts on)\b', ['blog'])
    }

    for content_type, (content_pattern, url_keywords) in patterns.items():
        if re.search(content_pattern, lower_content) or any(keyword in domain or keyword in path for keyword in url_keywords):
            return content_type

    if 'medium.com' in domain or metadata.get('author'):
        return "Article"

    return "Article"

# Metadata extraction functions
def extract_date(soup: BeautifulSoup) -> Optional[str]:
    """Extract the publication date from the soup object."""
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
    """Extract the author information from the soup object."""
    author_meta = soup.find('meta', attrs={'name': 'author'})
    author_url_meta = soup.find('meta', attrs={'property': 'article:author'})

    author_info = {}
    if author_meta:
        author_info['name'] = author_meta['content']
    if author_url_meta:
        author_info['url'] = author_url_meta['content']

    return author_info if author_info else None

def extract_metadata(soup: BeautifulSoup) -> Dict:
    """Extract metadata from the soup object."""
    return {
        'publication_date': extract_date(soup),
        'author': extract_author(soup)
    }

# Main parsing function
def parse_url(url: str, depth: int = 1) -> Dict:
    """
    Parse a URL and its linked pages up to the specified depth.
    """
    try:
        pages = []
        all_links = []
        visited = set()

        for current_depth in range(depth):
            if url in visited:
                break
            visited.add(url)

            soup = fetch_page(url)
            if not soup:
                print(f"Failed to fetch page: {url}")
                break

            main_content = find_main_content(soup)
            if not main_content:
                print(f"Failed to find main content for: {url}")
                break

            content = extract_content(main_content)
            metadata = extract_metadata(soup)

            # Get the text content for classification
            text_content = ' '.join([item['text'] for item in content if isinstance(item.get('text'), str)])

            # Classify the content
            content_type = classify_content(url, text_content, metadata)

            # Extract links from the entire page
            links = extract_links(soup, url)

            pages.append({
                "url": url,
                "content": content,
                "metadata": metadata,
                "content_type": content_type,
                "links": links[:10]
            })

            all_links.extend(links)

            if current_depth == depth - 1:
                break

            next_page = find_next_page(soup, url)
            if not next_page:
                break
            url = next_page

        unique_links = list({link['href']: link for link in all_links}.values())
        return {
            "pages": pages,
            "links": unique_links[:10 * depth]
        }
    except Exception as e:
        print(f"Error parsing URL: {str(e)}")
        return {"error": f"An error occurred while parsing the URL: {str(e)}"}

# Flask routes
@app.route('/save', methods=['POST'])
def save_content():
    """Save parsed content to a file."""
    try:
        content = request.json
        if 'url' not in content:
            return jsonify({"error": "URL is required"}), 400

        saves = load_saves()
        existing_save = next((save for save in saves if save.get('url') == content['url']), None)

        if existing_save:
            return jsonify({"message": "Content already saved", "id": existing_save['id']}), 200

        new_id = max([save.get('id', 0) for save in saves] + [0]) + 1
        content['id'] = new_id
        saves.append(content)

        save_to_file(saves)
        return jsonify({"message": "Content saved successfully", "id": new_id}), 200
    except Exception:
        return jsonify({"error": "An internal server error occurred"}), 500

@app.route('/saves', methods=['GET'])
def get_saves():
    """Retrieve all saved contents."""
    saves = load_saves()
    return jsonify(saves), 200

@app.route('/save/<int:id>', methods=['GET'])
def get_save(id):
    """Retrieve a specific saved content by ID."""
    saves = load_saves()
    save = next((save for save in saves if save['id'] == id), None)
    if save:
        return jsonify(save), 200
    return jsonify({"error": "Save not found"}), 404

@app.route('/remove/<int:id>', methods=['POST'])
def remove_content(id):
    """Remove a specific saved content by ID."""
    try:
        saves = load_saves()
        original_length = len(saves)
        saves = [save for save in saves if save['id'] != id]

        if len(saves) == original_length:
            return jsonify({"error": f"Content with id {id} not found"}), 404

        save_to_file(saves)
        return jsonify({"message": "Content removed successfully"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/remove-all', methods=['POST'])
def remove_all_content():
    """Remove all saved contents."""
    save_to_file([])
    return jsonify({"message": "All content removed successfully"}), 200

@app.route('/parse', methods=['POST'])
def parse():
    """Parse a URL and return the result."""
    data = request.json
    url = data.get('url')
    depth = int(data.get('depth', 1))

    if not url:
        return jsonify({"error": "URL is required"}), 400

    result = parse_url(url, depth)
    return jsonify(result)

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')

# File operations
def load_saves() -> List[Dict]:
    """Load saved contents from file."""
    if not os.path.exists(SAVES_FILE):
        os.makedirs(os.path.dirname(SAVES_FILE), exist_ok=True)
        save_to_file([])
    with open(SAVES_FILE) as f:
        return json.load(f)

def save_to_file(saves: List[Dict]):
    """Save contents to file."""
    os.makedirs(os.path.dirname(SAVES_FILE), exist_ok=True)
    with open(SAVES_FILE, 'w') as f:
        json.dump(saves, f)

if __name__ == "__main__":
    app.run(debug=True)
