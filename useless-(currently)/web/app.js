async function updateChat() {
    const response = await fetch("/messages");
    const messages = await response.json();

    const chat = document.getElementById("chat");
    chat.innerHTML = "";

    for (const message of messages) {
        chat.innerHTML += `
            <p id="message-other">
                <b>${message.author}</b>: ${message.content}
            </p>
        `;
    }
}

setInterval(updateChat, 500);
updateChat();