// Função para login
function login() {
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  fetch("/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  })
    .then(res => res.json())
    .then(data => {
      document.getElementById("message").textContent = data.message;
      if (data.redirect) {
        localStorage.setItem("loggedUser", username);
        window.location.href = data.redirect;
      }
    });
}

// Função para registro
function register() {
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  fetch("/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password })
  })
    .then(res => res.json())
    .then(data => {
      document.getElementById("message").textContent = data.message;
    });
}

// ⚠️ Apagar todos os usuários
function deleteAllUsers() {
  fetch('/delete-all-users', {
    method: 'DELETE',
  })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message || 'Todos os usuários foram apagados.');
    })
    .catch((err) => {
      alert('Erro ao apagar usuários.');
      console.error(err);
    });
}

// Upload de arquivo
function uploadFile() {
  const username = localStorage.getItem("loggedUser");
  const fileInput = document.getElementById("fileInput");

  if (!username || !fileInput.files.length) {
    alert("Usuário não autenticado ou nenhum arquivo selecionado.");
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("username", username);  // ⚠️ Essencial!

  fetch("/upload", {
    method: "POST",
    body: formData,
  })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message || "Upload feito!");
      listFiles();
      updateUsage();
    })
    .catch((err) => {
      alert("Erro ao enviar arquivo");
      console.error(err);
    });
}

// Listar arquivos do usuário logado
function listFiles() {
  const username = localStorage.getItem("loggedUser");
  fetch(`/files/${username}`)
    .then(res => res.json())
    .then(files => {
      const list = document.getElementById("fileList");
      list.innerHTML = "";

      if (files.length === 0) {
        list.innerHTML = "<li>Nenhum arquivo enviado ainda.</li>";
      } else {
        files.forEach(file => {
          const li = document.createElement("li");
          li.innerHTML = `<a href="/download/${username}/${file}" target="_blank">${file}</a>`;
          list.appendChild(li);
        });
      }
    });
}

// Atualizar barra de uso de armazenamento
function updateUsage() {
  const username = localStorage.getItem("loggedUser");
  fetch(`/usage/${username}`)
    .then(res => res.json())
    .then(data => {
      const usedMB = (data.used / (1024 * 1024)).toFixed(2);
      const limitMB = (data.limit / (1024 * 1024)).toFixed(2);
      const percent = ((data.used / data.limit) * 100).toFixed(1);

      const bar = document.getElementById("storageBar");
      bar.style.width = `${percent}%`;
      bar.textContent = `${percent}%`;

      document.getElementById("storageUsageText").textContent =
        `${usedMB} MB de ${limitMB} MB usados`;
    });
}

function logout() {
  localStorage.removeItem("loggedUser");
  window.location.href = "/";
}


// Inicialização da dashboard
document.addEventListener("DOMContentLoaded", () => {
  const username = localStorage.getItem("loggedUser");
  const usernameInput = document.getElementById("loggedUsername");

  if (usernameInput) {
    usernameInput.value = username;
  }

  if (username) {
    listFiles();
    updateUsage();
  }

  const uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    uploadForm.addEventListener("submit", (e) => {
      e.preventDefault();
      uploadFile();
    });
  }
});
