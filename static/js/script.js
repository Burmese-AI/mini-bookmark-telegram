document.addEventListener('DOMContentLoaded', () => {
    const elements = {
        urlForm: document.getElementById('url-form'),
        urlInput: document.getElementById('url-input'),
        resultDiv: document.getElementById('result'),
        contentTitle: document.getElementById('content-title'),
        contentType: document.getElementById('content-type'),
        contentBody: document.getElementById('content-body'),
        metadata: document.getElementById('metadata'),
        links: document.getElementById('links'),
        saveButton: document.getElementById('save-button'),
        errorMessageDiv: document.getElementById('error-message')
    };

    elements.urlForm.addEventListener('submit', handleSubmit);
    elements.saveButton.addEventListener('click', handleSave);

    async function handleSubmit(e) {
        e.preventDefault();
        const url = elements.urlInput.value;

        try {
            const data = await fetchParseResult(url);
            if (data.error) {
                displayError(data.error);
            } else {
                displayResult(data);
            }
        } catch (error) {
            displayError(error.message);
        }
    }

    async function fetchParseResult(url) {
        const response = await fetch('/parse', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        return await response.json();
    }

    function displayError(message) {
        elements.errorMessageDiv.textContent = `Error: ${message}`;
        elements.errorMessageDiv.style.display = 'block';
        elements.resultDiv.style.display = 'none';
        elements.saveButton.style.display = 'none';
    }

    function displayResult(data) {
        elements.errorMessageDiv.style.display = 'none';
        elements.resultDiv.style.display = 'block';
        elements.saveButton.style.display = 'block';

        elements.contentTitle.textContent = data.title || 'No title available';
        elements.contentType.textContent = `Content Type: ${data.type || 'Unknown'}`;
        displayContent(data.content);
        displayMetadata(data.metadata);
        displayLinks(data.links);
    }

    function displayContent(content) {
        if (Array.isArray(content) && content.length > 0) {
            elements.contentBody.innerHTML = content.map(renderContentItem).join('');
        } else {
            elements.contentBody.innerHTML = '<p>No content available</p>';
        }
    }

    function renderContentItem(item) {
        if (typeof item.text === 'string') {
            return `<${item.tag}>${item.text}</${item.tag}>`;
        } else if (Array.isArray(item.text)) {
            return `<${item.tag}>${item.text.map(renderContentItem).join('')}</${item.tag}>`;
        }
        return '';
    }

    function displayMetadata(metadata) {
        if (metadata && Object.keys(metadata).length > 0) {
            elements.metadata.innerHTML = '<h3>Metadata:</h3>' + 
                Object.entries(metadata)
                    .map(([key, value]) => `<p><strong>${key}:</strong> ${value || 'N/A'}</p>`)
                    .join('');
        } else {
            elements.metadata.innerHTML = '<p>No metadata available</p>';
        }
    }

    function displayLinks(links) {
        if (Array.isArray(links) && links.length > 0) {
            elements.links.innerHTML = '<h3>Links:</h3><ul>' + 
                links.map(link => `<li><a href="${link.href}" target="_blank">${link.text}</a></li>`).join('') + 
                '</ul>';
        } else {
            elements.links.innerHTML = '<p>No links available</p>';
        }
    }

    function handleSave() {
        const content = {
            title: elements.contentTitle.textContent,
            type: elements.contentType.textContent,
            content: elements.contentBody.innerHTML,
            metadata: elements.metadata.innerHTML,
            links: elements.links.innerHTML
        };
        localStorage.setItem('savedContent', JSON.stringify(content));
        alert('Content saved successfully!');
    }
});
