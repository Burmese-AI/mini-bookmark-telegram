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
    """Fetch and parse a web page with rate limiting."""
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
    """Identify and extract the main content from a parsed web page."""
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
    text = tag.get_text(strip=True)
    return {'tag': tag.name, 'text': text} if text and text not in blockquote_text else None

def extract_link_content(tag: BeautifulSoup, blockquote_text: set, base_url: str) -> Tuple[Optional[Dict], Optional[Dict]]:
    text = tag.get_text(strip=True)
    ignored_terms = ['sign up', 'sign in', 'follow', 'login', 'register', 'subscribe']

    if text.lower() not in blockquote_text and not any(term in text.lower() for term in ignored_terms):
        href = urljoin(base_url, tag.get('href')) if tag.get('href') else None
        content = {'tag': 'a', 'text': text, 'href': href}
        link = {'text': text, 'href': href}
        return content, link
    return None, None

def extract_strong_content(tag: BeautifulSoup, blockquote_text: set) -> Optional[Dict]:
    text = tag.get_text(strip=True)
    return {'tag': 'strong', 'text': text} if text not in blockquote_text else None

def extract_pre_content(tag: BeautifulSoup) -> Dict:
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
    list_items = [li.get_text(strip=True) for li in tag.find_all('li', recursive=False)
                  if li.get_text(strip=True) and li.get_text(strip=True) not in blockquote_text and not li.find('a')]
    return {'tag': tag.name, 'text': list_items} if list_items else None

def extract_blockquote_content(tag: BeautifulSoup, blockquote_text: set, base_url: str) -> Tuple[Optional[Dict], List[Dict]]:
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
    return ({'tag': 'blockquote', 'text': blockquote_content}, links) if blockquote_content else (None, links)

def extract_paragraph_content(tag: BeautifulSoup, blockquote_text: set, base_url: str, is_blockquote: bool = False) -> Tuple[Optional[Dict], List[Dict]]:
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

def filter_empty_headings(content: List[Dict]) -> List[Dict]:
    filtered_content = []
    for i, item in enumerate(content):
        if item['tag'].startswith('h'):
            if i == len(content) - 1 or content[i+1]['tag'].startswith('h'):
                continue
        filtered_content.append(item)
    return filtered_content

def extract_content(soup: BeautifulSoup, base_url: str) -> Tuple[List[Dict], List[Dict]]:
    content = []
    links = []
    blockquote_text = set()
    main_content = find_main_content(soup) or soup.body or soup

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

    filtered_content = filter_empty_headings(content)
    return filtered_content, links

def classify_content(url: str, content: str, metadata: dict) -> str:
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

def extract_date(soup: BeautifulSoup) -> Optional[str]:
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
    author_meta = soup.find('meta', attrs={'name': 'author'})
    author_url_meta = soup.find('meta', attrs={'property': 'article:author'})

    author_info = {}
    if author_meta:
        author_info['name'] = author_meta['content']
    if author_url_meta:
        author_info['url'] = author_url_meta['content']

    return author_info if author_info else None

def extract_metadata(soup: BeautifulSoup) -> Dict:
    return {
        'publication_date': extract_date(soup),
        'author': extract_author(soup)
    }

def parse_url(url: str) -> Dict:
    try:
        soup = fetch_page(url)
        if soup is None:
            return {"error": "Failed to fetch the page", "content": []}

        base_url = '/'.join(url.split('/')[:3])
        content_text, additional_links = extract_content(soup, base_url)

        if not content_text:
            return {"error": "No content could be extracted from this page", "content": []}

        metadata = extract_metadata(soup)
        content_type = classify_content(url, ' '.join([item['text'] for item in content_text if isinstance(item['text'], str)]), metadata)

        ignored_terms = ['sign up', 'sign in', 'follow', 'login', 'register', 'subscribe', 'open in app']
        all_links = soup.find_all('a', href=True)
        filtered_links = [
            {'text': a.get_text(strip=True), 'href': urljoin(base_url, a['href'])}
            for a in all_links
            if a.get_text(strip=True) and not any(term in a.get_text(strip=True).lower() for term in ignored_terms)
        ]

        filtered_links.extend(additional_links)
        unique_links = list({link['href']: link for link in filtered_links}.values())[:10]

        return {
            "content": content_text,
            "type": content_type,
            "metadata": metadata,
            "links": unique_links
        }
    except Exception as e:
        return {"error": f"An error occurred while parsing the URL: {str(e)}", "content": []}

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
    """Parse a given URL and return its content."""
    url = request.json.get('url')
    if not url:
        return jsonify({"error": "URL is required", "content": []}), 400
    try:
        result = parse_url(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "content": []}), 500

@app.route('/')
def index():
    """Render the main page."""
    return render_template('index.html')

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
