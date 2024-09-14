document.addEventListener('DOMContentLoaded', () => {
    const urlForm = document.getElementById('url-form');
    const urlInput = document.getElementById('url-input');
    const inputContainer = document.getElementById('input-container');
    const loadingDiv = document.getElementById('loading');
    const resultDiv = document.getElementById('result');

    urlForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const url = urlInput.value;

        inputContainer.style.display = 'none';
        loadingDiv.style.display = 'block';
        resultDiv.style.display = 'none';

        try {
            const response = await fetch('/parse', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ url }),
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const data = await response.json();

            loadingDiv.style.display = 'none';
            resultDiv.style.display = 'block';

            if (data.error) {
                resultDiv.innerHTML = `<p class="error">${data.error}</p>`;
            } else {
                displayResult(data);
            }
        } catch (error) {
            loadingDiv.style.display = 'none';
            resultDiv.style.display = 'block';
            resultDiv.innerHTML = `<p class="error">An error occurred: ${error.message}</p>`;
            console.error('Error:', error);
        }
    });

    function displayResult(data) {
        let html = '<div class="article-meta">';
        
        if (data.type) {
            html += `<p><strong>Type:</strong> ${escapeHtml(data.type)}</p>`;
        }
        
        if (data.metadata) {
            if (data.metadata.author) {
                let authorText = data.metadata.author;
                if (typeof authorText === 'object') {
                    authorText = authorText.name || JSON.stringify(authorText);
                }
                html += `<p><strong>Author:</strong> ${escapeHtml(authorText)}</p>`;
            }
            if (data.metadata.publication_date) {
                html += `<p><strong>Publication Date:</strong> ${escapeHtml(data.metadata.publication_date)}</p>`;
            }
        }
        
        html += '</div>';

        if (data.content && Array.isArray(data.content)) {
            // Assuming the first h1 or h2 is the title
            const titleItem = data.content.find(item => item.tag === 'h1' || item.tag === 'h2');
            if (titleItem) {
                html += `<h1 class="article-title">${escapeHtml(titleItem.text)}</h1>`;
                // Remove the title from the content array
                data.content = data.content.filter(item => item !== titleItem);
            }

            html += '<div class="article-content">';
            html += renderContent(data.content);
            html += '</div>';
        }

        // Add links section
        if (data.links && data.links.length > 0) {
            html += '<div class="article-links">';
            html += '<h3>Related Links:</h3>';
            html += '<ul class="link-list">';
            data.links.forEach(link => {
                html += `
                    <li class="link-item">
                        <a href="${escapeHtml(link.href)}" target="_blank" class="link-anchor">
                            <span class="link-text">${escapeHtml(link.text)}</span>
                            <span class="link-arrow">→</span>
                        </a>
                    </li>
                `;
            });
            html += '</ul>';
            html += '</div>';
        }

        resultDiv.innerHTML = html;
    }

    function filterContent(content, linkTexts) {
        console.log("Filtering content:", JSON.stringify(content, null, 2));
        console.log("Link texts:", linkTexts);

        return content.filter(item => {
            if (typeof item.text === 'string') {
                const itemText = item.text.toLowerCase();
                const shouldKeep = !linkTexts.some(linkText => 
                    itemText.includes(linkText) || 
                    linkText.includes(itemText) ||
                    itemText.length > 10 && linkText.length > 10 && 
                    (itemText.substring(0, 10) === linkText.substring(0, 10))
                );
                console.log(`Checking item: ${itemText}, Keep: ${shouldKeep}`);
                return shouldKeep;
            } else if (Array.isArray(item.text)) {
                item.text = filterContent(item.text, linkTexts);
                return item.text.length > 0;
            } else if (item.text && typeof item.text === 'object') {
                const itemText = item.text.text.toLowerCase();
                const shouldKeep = !linkTexts.some(linkText => 
                    itemText.includes(linkText) || 
                    linkText.includes(itemText) ||
                    itemText.length > 10 && linkText.length > 10 && 
                    (itemText.substring(0, 10) === linkText.substring(0, 10))
                );
                console.log(`Checking item: ${itemText}, Keep: ${shouldKeep}`);
                return shouldKeep;
            }
            return true;
        });
    }

    function renderContent(content) {
        if (!Array.isArray(content)) {
            console.error('Content is not an array:', content);
            return '<p>Error: Unable to render content</p>';
        }

        return content.map(item => {
            if (!item || typeof item !== 'object') {
                return '';
            }

            if (item.tag === 'pre') {
                return renderPreContent(item);
            } else if (item.tag === 'blockquote') {
                return renderBlockquoteContent(item);
            } else if (typeof item.text === 'string') {
                return `<${item.tag}>${escapeHtml(item.text)}</${item.tag}>`;
            } else if (Array.isArray(item.text)) {
                let innerContent = renderContent(item.text);
                return `<${item.tag}>${innerContent}</${item.tag}>`;
            } else if (item.text && typeof item.text === 'object' && item.text.text) {
                return `<${item.tag}>${escapeHtml(item.text.text)}</${item.tag}>`;
            }
            return '';
        }).join('\n\n');
    }

    function renderBlockquoteContent(item) {
        if (!Array.isArray(item.text)) {
            return `<blockquote>${escapeHtml(item.text)}</blockquote>`;
        }
        let blockquoteContent = item.text.map(innerItem => {
            if (typeof innerItem === 'string') {
                return `<p>${escapeHtml(innerItem)}</p>`;
            }
            if (innerItem.tag === 'p') {
                return renderContent([innerItem]);
            }
            if (innerItem.tag === 'br') {
                return '<br>';
            }
            if (innerItem.tag === null) {
                return escapeHtml(innerItem.text);
            }
            return `<${innerItem.tag}>${escapeHtml(innerItem.text)}</${innerItem.tag}>`;
        }).join('');
        return `<blockquote>${blockquoteContent}</blockquote>`;
    }

    function renderPreContent(item) {
        if (Array.isArray(item.text)) {
            return `<pre>${item.text.map(renderPreItem).join('')}</pre>`;
        }
        return `<pre>${escapeHtml(JSON.stringify(item.text, null, 2))}</pre>`;
    }

    function renderPreItem(preItem) {
        if (typeof preItem === 'string') {
            return escapeHtml(preItem);
        }
        if (preItem.tag === 'span') {
            return `<span>${Array.isArray(preItem.content) ? preItem.content.map(renderPreItem).join('') : escapeHtml(preItem.content)}</span>`;
        }
        if (preItem.tag === 'br') {
            return '\n';
        }
        if (preItem.tag === null) {
            return escapeHtml(preItem.text);
        }
        return `<${preItem.tag}>${escapeHtml(preItem.text || '')}</${preItem.tag}>`;
    }

    function escapeHtml(unsafe) {
        if (unsafe === null || unsafe === undefined) {
            return '';
        }
        if (typeof unsafe !== 'string') {
            unsafe = String(unsafe);
        }
        return unsafe
             .replace(/&/g, "&amp;")
             .replace(/</g, "&lt;")
             .replace(/>/g, "&gt;")
             .replace(/"/g, "&quot;")
             .replace(/'/g, "&#039;");
    }
});
