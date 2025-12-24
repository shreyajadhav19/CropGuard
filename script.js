// static/js/script.js

// 🌈 Animate cards on hover (subtle scale effect)
document.addEventListener("DOMContentLoaded", () => {
  const cards = document.querySelectorAll(".card");
  cards.forEach(card => {
    card.addEventListener("mouseover", () => {
      card.style.transform = "scale(1.05)";
      card.style.boxShadow = "0 4px 20px rgba(40,49,6,0.3)";
    });
    card.addEventListener("mouseout", () => {
      card.style.transform = "scale(1)";
      card.style.boxShadow = "none";
    });
  });
});

// 🧭 Smooth scroll for internal navigation (if needed)
const smoothScrollLinks = document.querySelectorAll('a[href^="#"]');
smoothScrollLinks.forEach(link => {
  link.addEventListener("click", function (e) {
    e.preventDefault();
    const target = document.querySelector(this.getAttribute("href"));
    if (target) {
      target.scrollIntoView({ behavior: "smooth" });
    }
  });
});

// 💬 Chatbot functionality (used in chatbot.html)
async function sendChatMessage() {
  const userInput = document.getElementById("user-input").value.trim();
  if (!userInput) return;

  const chatBox = document.getElementById("chat-box");
  chatBox.innerHTML += `<div class='user-msg'><b>You:</b> ${userInput}</div>`;
  document.getElementById("user-input").value = "";

  try {
    const response = await fetch("/get_response", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: userInput })
    });
    const data = await response.json();
    chatBox.innerHTML += `<div class='bot-msg'><b>Bot:</b> ${data.reply}</div>`;
  } catch (error) {
    chatBox.innerHTML += `<div class='bot-msg'><b>Bot:</b> Sorry, I couldn’t connect right now.</div>`;
  }

  chatBox.scrollTop = chatBox.scrollHeight; // Auto scroll
}

// Optional: Handle Enter key for sending messages
document.addEventListener("keypress", (event) => {
  if (event.key === "Enter" && document.activeElement.id === "user-input") {
    sendChatMessage();
  }
});
