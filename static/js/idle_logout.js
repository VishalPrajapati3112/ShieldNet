let idleTime = 0;

document.addEventListener("mousemove", resetTimer);
document.addEventListener("keypress", resetTimer);
document.addEventListener("click", resetTimer);

function resetTimer() {
    idleTime = 0;
    fetch("/ping", { method: "POST" });
}

setInterval(() => {
    idleTime += 1;
    if (idleTime > 300) {  // 5 minutes
        window.location.href = "/logout";
    }
}, 1000);
