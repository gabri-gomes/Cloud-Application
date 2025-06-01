// Função para login
function login() {
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  fetch("/login", {
    method: "POST",
    credentials: "same-origin",
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
  formData.append("username", username);

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
          li.innerHTML = `
          <a href="/download/${username}/${file}" target="_blank">${file}</a>
          <button onclick="deleteFile('${file}')">❌ Apagar</button>
          `;

          list.appendChild(li);
        });
      }
    });
}

function deleteFile(filename) {
  const username = localStorage.getItem("loggedUser");

  fetch("/delete-file", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, filename }),
  })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message);
      listFiles();
      updateUsage();
    });
}

function deleteAllFiles() {
  const username = localStorage.getItem("loggedUser");

  if (!confirm("Tens a certeza que queres apagar TODOS os ficheiros?")) return;

  fetch("/delete-all-files", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  })
    .then((res) => res.json())
    .then((data) => {
      alert(data.message);
      listFiles();
      updateUsage();
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

// Submissão de job
function setupJobForm() {
  const jobForm = document.getElementById("jobForm");
  if (jobForm) {
    jobForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const username = localStorage.getItem("loggedUser");
      const jobInput = document.getElementById("jobInput");
      const inputFile = document.getElementById("inputFile"); // ← NOVO

      if (!username || !jobInput.files.length) {
        alert("Usuário ou job não especificado.");
        return;
      }

      const formData = new FormData();
      formData.append("username", username);
      formData.append("job", jobInput.files[0]);

      if (inputFile.files.length > 0) {
        formData.append("input", inputFile.files[0]); // ← NOVO
      }

      fetch("/submit-job", {
        method: "POST",
        body: formData,
      })
        .then((res) => res.json())
        .then((data) => {
          alert(data.message || "Job executado.");
          loadJobs();
        });
    });
  }
}


function loadJobs() {
  const username = localStorage.getItem("loggedUser");
  const jobList = document.getElementById("jobResults");

  if (!jobList) return;

  fetch(`/jobs/${username}`)
    .then((res) => res.json())
    .then((jobs) => {
      jobList.innerHTML = "";
      if (jobs.length === 0) {
        jobList.innerHTML = "<li>Nenhum job executado ainda.</li>";
      } else {
        jobs.forEach((job) => {
          const li = document.createElement("li");
          li.innerHTML = `<strong>${job.job}</strong><pre>${job.output}</pre>`;
          jobList.appendChild(li);
        });
      }
    });
}


// Inicialização da dashboard
document.addEventListener("DOMContentLoaded", () => {
  // Mostra o nome do utilizador logado
  const username = localStorage.getItem("loggedUser");
  const usernameInput = document.getElementById("loggedUsername");
  if (usernameInput) {
    usernameInput.textContent = username;
  }

  // Se já estiver logado, carrega ficheiros, uso e jobs
  if (username) {
    listFiles();
    updateUsage();
    loadJobs();
  }

  // Upload de ficheiro
  const uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    uploadForm.addEventListener("submit", (e) => {
      e.preventDefault();
      uploadFile();
    });
  }

  // Submissão de job de script
  setupJobForm();

  // Submissão de job Dask
  const daskForm = document.getElementById("daskJobForm");
  if (daskForm) {
    daskForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const zipFile  = document.getElementById("daskZip").files[0];
      const mainFile = document.getElementById("daskMainFile").value;
      const user     = localStorage.getItem("loggedUser");

      if (!zipFile || !mainFile || !user) {
        alert("Preencha todos os campos.");
        return;
      }

      const formData = new FormData();
      formData.append("zip", zipFile);
      formData.append("mainFile", mainFile);
      formData.append("username", user);

      try {
        const res    = await fetch("/submit-dask-job", { method: "POST", body: formData });
        const result = await res.json();
        document.getElementById("daskJobOutput").innerText = result.message;
      } catch (err) {
        console.error("Erro:", err);
        document.getElementById("daskJobOutput").innerText = "Erro inesperado.";
      }
    });
  }

  // Submissão de container
  const containerForm = document.getElementById("containerForm");
  if (containerForm) {
    containerForm.addEventListener("submit", async (e) => {
      e.preventDefault();

      const img = document.getElementById("ctrImage").value;
      const cmd = document.getElementById("ctrCmd").value;

      const res = await fetch("/run-container", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ image: img, command: cmd })
      });
      const { job_name } = await res.json();
      document.getElementById("ctrLogs").textContent = `Job ${job_name} enfileirado…`;

      // Polling para mostrar logs assim que estiverem disponíveis
      (async function poll() {
        const r2 = await fetch(`/job-container-logs?job_name=${job_name}`);
        if (r2.status === 200) {
          const { logs } = await r2.json();
          document.getElementById("ctrLogs").textContent = logs;
        } else {
          setTimeout(poll, 1000);
        }
      })();
    });
  }
});


