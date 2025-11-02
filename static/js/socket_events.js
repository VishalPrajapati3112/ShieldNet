var socket = io.connect(window.location.origin);
let token = null;

function joinSession(t) {
  token = t;
  socket.emit('join_room', { token: token });
}

socket.on('participants_update', function(data) {
  let list = document.getElementById("participants");
  list.innerHTML = "";
  data.participants.forEach(p => {
    let li = document.createElement("li");
    li.textContent = p;
    list.appendChild(li);
  });
});

socket.on('session_ended', function() {
  alert("Session ended by sender!");
  window.location.href = "/online";
});
