document.addEventListener('DOMContentLoaded', () => {
    // Constants and global variables
    const API_ENDPOINTS = {
        SAVES: '/saves',
        PARSE: '/parse',
        SAVE: '/save',
        REMOVE: (id) => `/remove/${id}`
    };

    let currentContent = null;
    let currentUrl = null;
    let inputContainer, loadingDiv, resultDiv;

    // DOM elements
    const urlForm = document.getElementById('url-form');
    const urlInput = document.getElementById('url-input');
    const savesButton = document.getElementById('saves-button');
    inputContainer = document.getElementById('input-container');
    loadingDiv = document.getElementById('loading');
    resultDiv = document.getElementById('result');

    // Event listeners
    urlForm.addEventListener('submit', handleFormSubmit);
    savesButton.addEventListener('click', showSaves);

    // Toast functionality
    const toastContainer = createToastContainer();

    function createToastContainer() {
        const container = document.createElement('div');
        container.className = 'toast-container';
        document.body.appendChild(container);
        return container;
    }

    function showToast(message, type = 'success', duration = 3000) {
        const toast = document.createElement('div');
        toast.className = `toast toast-${type}`;
        
        const text = document.createElement('p');
        text.className = 'toast-message';
        text.textContent = message;
        
        const progress = document.createElement('div');
        progress.className = 'toast-progress';
        
        toast.appendChild(text);
        toast.appendChild(progress);
        toastContainer.appendChild(toast);
        
        toast.offsetHeight;
        toast.classList.add('show');
        
        setTimeout(() => removeToast(toast), duration);
    }
    
    function removeToast(toast) {
        toast.classList.remove('show');
        setTimeout(() => {
            toastContainer.removeChild(toast);
        }, 400);
    }

    // Main functionality
    async function handleFormSubmit(e) {
        e.preventDefault();
        const url = urlInput.value;
        await fetchAndDisplayContent(url);
    }

    async function fetchAndDisplayContent(url) {
        currentUrl = url;
        const depthSelect = document.getElementById('depth-select');
        const depth = depthSelect.value;

        inputContainer.style.display = 'none';
        loadingDiv.style.display = 'block';
        resultDiv.style.display = 'none';

        try {
            const response = await fetch(API_ENDPOINTS.PARSE, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url, depth }),
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json();

            loadingDiv.style.display = 'none';

            if (data.error) {
                showToast(data.error, 'error');
                goBack();
            } else if (data.pages && data.pages.length > 0) {
                resultDiv.style.display = 'block';
                displayResult(data);
            } else {
                showToast('Failed to extract content from the page.', 'error');
                goBack();
            }
        } catch (error) {
            loadingDiv.style.display = 'none';
            showToast(`An error occurred: ${error.message}`, 'error');
            goBack();
        }
    }

    function displayResult(data) {
        let html = '<div class="article-meta">';
        
        // Metadata display
        if (data.pages && data.pages.length > 0) {
            const firstPage = data.pages[0];
            
            if (firstPage.content_type) html += `<p><strong>Content Type:</strong> ${escapeHtml(firstPage.content_type)}</p>`;
            
            if (firstPage.metadata) {
                if (firstPage.metadata.author) {
                    const author = firstPage.metadata.author;
                    const authorName = author.name ? escapeHtml(author.name) : null;
                    const authorUrl = author.url || null;

                    if (authorName && authorUrl) {
                        html += `<p><strong>Author:</strong> <a href="${escapeHtml(authorUrl)}" target="_blank" class="author-link">${authorName}</a></p>`;
                    } else if (authorName) {
                        html += `<p><strong>Author:</strong> ${authorName}</p>`;
                    }
                }
                
                if (firstPage.metadata.publication_date) {
                    html += `<p><strong>Publication Date:</strong> ${escapeHtml(firstPage.metadata.publication_date)}</p>`;
                }
            }
        }
        
        html += '</div>';

        // Display content from all pages
        if (data.pages && data.pages.length > 0) {
            data.pages.forEach((page, index) => {
                if (data.pages.length > 1) {
                    html += `<h2 class="page-heading">Page ${index + 1}</h2>`;
                }
                if (page.content && Array.isArray(page.content)) {
                    const titleItem = page.content.find(item => item.tag === 'h1' || item.tag === 'h2');
                    html += '<div class="article-content">';
                    html += renderContent(page.content);
                    html += '</div>';
                }
            });
        }

        // Display all links together
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
            html += '</ul></div>';
        }

        html += '<div class="content-footer">';
        html += '<button id="back-button" class="action-button back-button">Back</button>';
        
        html += data.id
            ? `<button id="remove-button" class="action-button remove-button">Remove Content</button>`
            : `<button id="save-button" class="action-button save-button">Save Content</button>`;
        
        html += '</div>';

        resultDiv.innerHTML = html;

        document.getElementById('back-button').addEventListener('click', goBack);
        
        if (data.id) {
            document.getElementById('remove-button').addEventListener('click', () => removeSavedContent(data.id));
        } else {
            document.getElementById('save-button').addEventListener('click', () => {
                const saveData = { url: currentUrl, content: data };
                saveContent(saveData);
            });
        }

        currentContent = data;
    }

    async function showSaves() {
        try {
            const response = await fetch(API_ENDPOINTS.SAVES);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const saves = await response.json();
            displaySaves(saves);
        } catch (error) {
            showToast('Failed to fetch saves. Please try again.', 'error');
        }
    }

    function displaySaves(saves) {
        inputContainer.style.display = 'none';
        resultDiv.style.display = 'block';

        let html = '<h2>Saved Contents</h2>';
        if (saves.length === 0) {
            html += '<p>No saved content yet.</p>';
        } else {
            html += '<ul id="saves-list">';
            saves.forEach(save => {
                const url = save.url || (save.content && save.content.url) || 'URL not found';
                html += `
                    <li>
                        <div class="url-container">
                            <span class="url" title="${escapeHtml(url)}">${escapeHtml(url)}</span>
                        </div>
                        <div class="button-container">
                            <button class="action-button view-button" data-id="${save.id}">View</button>
                            <button class="action-button remove-button" data-id="${save.id}">Remove</button>
                        </div>
                    </li>`;
            });
            html += '</ul>';
        }
        html += '<button id="back-button" class="action-button back-button">Back</button>';

        resultDiv.innerHTML = html;

        document.querySelectorAll('.view-button').forEach(button => {
            button.addEventListener('click', (e) => displaySavedContent(e.target.dataset.id));
        });

        document.querySelectorAll('.remove-button').forEach(button => {
            button.addEventListener('click', (e) => removeSavedContent(e.target.dataset.id));
        });

        document.getElementById('back-button').addEventListener('click', goBack);
    }

    async function saveContent(data) {
        try {
            const saveData = { url: currentUrl, ...data };
            const response = await fetch(API_ENDPOINTS.SAVE, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(saveData),
            });

            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const result = await response.json();
            showToast('Content saved successfully!', 'success');
            
            if (result.id) {
                data.id = result.id;
                addRemoveButton(result.id);
            }
        } catch (error) {
            showToast('Failed to save content. Please try again.', 'error');
        }
    }

    async function removeSavedContent(id) {
        if (id === undefined) {
            showToast('Error: Unable to remove content due to missing ID', 'error');
            return;
        }

        try {
            const response = await fetch(API_ENDPOINTS.REMOVE(id), { method: 'POST' });

            const contentType = response.headers.get("content-type");
            let result;
            if (contentType && contentType.indexOf("application/json") !== -1) {
                result = await response.json();
            } else {
                const text = await response.text();
                throw new Error(`Server responded with non-JSON content: ${text}`);
            }

            if (!response.ok) {
                throw new Error(`Server responded with status ${response.status}: ${result.error || 'Unknown error'}`);
            }

            showToast('Content removed successfully!', 'remove');

            const savesList = document.getElementById('saves-list');
            if (savesList) {
                showSaves();
            } else {
                updateButtonsAfterRemove();
            }
        } catch (error) {
            showToast(`Failed to remove content: ${error.message}`, 'error');
        }
    }

    function updateButtonsAfterRemove() {
        const removeButton = document.getElementById('remove-button');
        if (removeButton) removeButton.remove();

        const saveButton = document.createElement('button');
        saveButton.id = 'save-button';
        saveButton.className = 'action-button save-button';
        saveButton.textContent = 'Save Content';
        saveButton.addEventListener('click', () => saveContent(currentContent));

        const contentFooter = document.querySelector('.content-footer');
        if (contentFooter) contentFooter.appendChild(saveButton);

        if (currentContent) delete currentContent.id;
    }

    async function displaySavedContent(id) {
        try {
            const response = await fetch(`${API_ENDPOINTS.SAVE}/${id}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            inputContainer.style.display = 'none';
            resultDiv.style.display = 'block';
            displayResult(data.content ? { ...data.content, id: data.id } : data);
        } catch (error) {
            showToast('Failed to fetch saved content. Please try again.', 'error');
        }
    }

    function goBack() {
        inputContainer.style.display = 'block';
        resultDiv.style.display = 'none';
        resultDiv.innerHTML = '';
        urlInput.value = '';
    }

    // Content rendering functions
    function renderContent(content) {
        if (!Array.isArray(content)) return '<p>Error: Unable to render content</p>';

        return content.map(item => {
            if (!item || typeof item !== 'object') return '';

            if (item.tag === 'pre') return renderPreContent(item);
            if (item.tag === 'blockquote') return renderBlockquoteContent(item);
            
            return renderTag(item);
        }).join('\n\n');
    }

    function renderTag(item) {
        if (Array.isArray(item.text)) {
            const innerContent = item.text.map(innerItem => {
                if (innerItem.tag) {
                    return `<${innerItem.tag}>${escapeHtml(innerItem.text)}</${innerItem.tag}>`;
                }
                return escapeHtml(innerItem.text);
            }).join('');
            return `<${item.tag}>${innerContent}</${item.tag}>`;
        }
        
        return `<${item.tag}>${escapeHtml(item.text)}</${item.tag}>`;
    }

    function renderBlockquoteContent(item) {
        if (!Array.isArray(item.text)) return `<blockquote>${escapeHtml(item.text)}</blockquote>`;
        
        const blockquoteContent = item.text.map(innerItem => renderTag(innerItem)).join('');
        return `<blockquote>${blockquoteContent}</blockquote>`;
    }

    function renderPreContent(item) {
        if (Array.isArray(item.text)) return `<pre>${item.text.map(renderPreItem).join('')}</pre>`;
        return `<pre>${escapeHtml(JSON.stringify(item.text, null, 2))}</pre>`;
    }

    function renderPreItem(preItem) {
        if (typeof preItem === 'string') return escapeHtml(preItem);
        if (preItem.tag === 'span') return `<span>${Array.isArray(preItem.content) ? preItem.content.map(renderPreItem).join('') : escapeHtml(preItem.content)}</span>`;
        if (preItem.tag === 'br') return '\n';
        if (preItem.tag === null) return escapeHtml(preItem.text);
        return `<${preItem.tag}>${escapeHtml(preItem.text || '')}</${preItem.tag}>`;
    }

    function escapeHtml(unsafe) {
        if (unsafe === null || unsafe === undefined) return '';
        if (typeof unsafe !== 'string') unsafe = String(unsafe);
        return unsafe
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function addRemoveButton(id) {
        if (id === undefined) return;

        const saveButton = document.getElementById('save-button');
        if (saveButton) saveButton.remove();

        const existingRemoveButton = document.getElementById('remove-button');
        if (!existingRemoveButton) {
            const removeButton = document.createElement('button');
            removeButton.id = 'remove-button';
            removeButton.className = 'action-button remove-button';
            removeButton.textContent = 'Remove Content';
            removeButton.addEventListener('click', () => removeSavedContent(id));

            const contentFooter = document.querySelector('.content-footer');
            if (contentFooter) contentFooter.appendChild(removeButton);
        }
    }
});

