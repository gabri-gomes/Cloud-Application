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
    })
    .catch(err => {
      console.error("Erro no login:", err);
      document.getElementById("message").textContent = "Erro ao conectar-se ao servidor.";
    });
}

// Função para registo
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
    })
    .catch(err => {
      console.error("Erro no registo:", err);
      document.getElementById("message").textContent = "Erro ao conectar-se ao servidor.";
    });
}

// Apagar todos os usuários (rota DELETE /delete-all-users)
function deleteAllUsers() {
  fetch('/delete-all-users', { method: 'DELETE' })
    .then(res => res.json())
    .then(data => {
      alert(data.message || 'Todos os usuários foram apagados.');
    })
    .catch(err => {
      alert('Erro ao apagar usuários.');
      console.error(err);
    });
}

// Upload de arquivo
function uploadFile() {
  const username  = localStorage.getItem("loggedUser");
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
    .then(res => res.json())
    .then(data => {
      alert(data.message || "Upload feito!");
      listFiles();
      updateUsage();
    })
    .catch(err => {
      alert("Erro ao enviar arquivo");
      console.error(err);
    });
}

// Listar arquivos do usuário logado
function listFiles() {
  const username = localStorage.getItem("loggedUser");
  if (!username) return;

  fetch(`/files/${username}`)
    .then(res => res.json())
    .then(files => {
      const list = document.getElementById("fileList");
      list.innerHTML = "";

      if (!Array.isArray(files) || files.length === 0) {
        list.innerHTML = "<li>Nenhum arquivo enviado ainda.</li>";
      } else {
        files.forEach(file => {
          const li = document.createElement("li");
          li.innerHTML = `
            <a href="/download/${username}/${file}" target="_blank">${file}</a>
            <button onclick="deleteFile('${file}')"> Apagar</button>
          `;
          list.appendChild(li);
        });
      }
    })
    .catch(err => {
      console.error("Erro ao listar arquivos:", err);
    });
}

// Apagar um arquivo específico
function deleteFile(filename) {
  const username = localStorage.getItem("loggedUser");
  if (!username) return;

  fetch("/delete-file", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ username, filename })
  })
    .then(res => res.json())
    .then(data => {
      alert(data.message);
      listFiles();
      updateUsage();
    })
    .catch(err => {
      console.error("Erro ao apagar arquivo:", err);
    });
}

// Apagar todos os arquivos do usuário
function deleteAllFiles() {
  const username = localStorage.getItem("loggedUser");
  if (!username) return;

  if (!confirm("Tens a certeza que queres apagar TODOS os ficheiros?")) return;

  fetch("/delete-all-files", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ username })
  })
    .then(res => res.json())
    .then(data => {
      alert(data.message);
      listFiles();
      updateUsage();
    })
    .catch(err => {
      console.error("Erro ao apagar todos arquivos:", err);
    });
}

// Atualizar barra de uso de armazenamento
function updateUsage() {
  const username = localStorage.getItem("loggedUser");
  if (!username) return;

  fetch(`/usage/${username}`)
    .then(res => res.json())
    .then(data => {
      const usedMB  = (data.used  / (1024 * 1024)).toFixed(2);
      const limitMB = (data.limit / (1024 * 1024)).toFixed(2);
      const percent = data.limit > 0
        ? ((data.used / data.limit) * 100).toFixed(1)
        : "0.0";

      const bar = document.getElementById("storageBar");
      bar.style.width   = `${percent}%`;
      bar.textContent   = `${percent}%`;

      document.getElementById("storageUsageText").textContent =
        `${usedMB} MB de ${limitMB} MB usados`;
    })
    .catch(err => {
      console.error("Erro ao obter uso de armazenamento:", err);
    });
}

// Logout (remove localStorage e redireciona para página inicial)
function logout() {
  localStorage.removeItem("loggedUser");
  window.location.href = "/";
}

// Configura a submissão do formulário de jobs de script (rota /submit-job)
function setupJobForm() {
  const jobForm = document.getElementById("jobForm");
  if (!jobForm) return;

  jobForm.addEventListener("submit", e => {
    e.preventDefault();
    const username = localStorage.getItem("loggedUser");
    const jobInput = document.getElementById("jobInput");
    const inputFile = document.getElementById("inputFile");

    if (!username || !jobInput.files.length) {
      alert("Usuário ou job não especificado.");
      return;
    }

    const formData = new FormData();
    formData.append("username", username);
    formData.append("job", jobInput.files[0]);
    if (inputFile.files.length > 0) {
      formData.append("input", inputFile.files[0]);
    }

    fetch("/submit-job", {
      method: "POST",
      body: formData,
    })
      .then(res => res.json())
      .then(data => {
        alert(data.message || "Job executado.");
        loadJobs();
      })
      .catch(err => {
        console.error("Erro ao submeter job:", err);
      });
  });
}

// Carrega resultados dos jobs para a lista (<ul id="jobResults">)
function loadJobs() {
  const username = localStorage.getItem("loggedUser");
  const jobList  = document.getElementById("jobResults");
  if (!username || !jobList) return;

  fetch(`/jobs/${username}`)
    .then(res => res.json())
    .then(jobs => {
      jobList.innerHTML = "";
      if (!Array.isArray(jobs) || jobs.length === 0) {
        jobList.innerHTML = "<li>Nenhum job executado ainda.</li>";
      } else {
        jobs.forEach(job => {
          const li = document.createElement("li");
          li.innerHTML = `<strong>${job.job}</strong><pre>${job.output}</pre>`;
          jobList.appendChild(li);
        });
      }
    })
    .catch(err => {
      console.error("Erro ao carregar jobs:", err);
    });
}

// Busca e exibe a lista de databases no <ul id="dbList"> e no <select id="dbSelect">
async function fetchDatabases() {
  const listError = document.getElementById('listErrorDb');
  if (listError) listError.style.display = 'none';

  try {
    const resp = await fetch('/databases', {
      method: 'GET',
      credentials: 'same-origin'
    });
    if (!resp.ok) throw new Error('Falha ao obter lista de bases.');

    const data = await resp.json();

    // Preencher <ul id="dbList">
    const ul = document.getElementById('dbList');
    if (ul) {
      ul.innerHTML = '';
      data.databases.forEach(name => {
        const li = document.createElement('li');
        li.textContent = name;
        ul.appendChild(li);
      });
    }

    // Preencher <select id="dbSelect"> (se existir)
    const sel = document.getElementById('dbSelect');
    if (sel) {
      sel.innerHTML = '<option value="">-- escolha a base --</option>';
      data.databases.forEach(name => {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        sel.appendChild(opt);
      });
    }
  } catch (err) {
    if (listError) {
      listError.textContent = err.message;
      listError.style.display = 'block';
    }
    console.error(err);
  }
}

// Submissão do formulário de criação de database (<form id="createDbForm">)
function setupCreateDbForm() {
  const form = document.getElementById('createDbForm');
  if (!form) return;

  form.addEventListener('submit', async e => {
    e.preventDefault();
    const listError = document.getElementById('listErrorDb');
    if (listError) listError.style.display = 'none';

    const inputName = document.getElementById('newDbName');
    const nome      = inputName.value.trim();
    if (!nome) {
      if (listError) {
        listError.textContent = 'Digite um nome válido.';
        listError.style.display = 'block';
      }
      return;
    }

    try {
      const resp = await fetch('/databases', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dbname: nome })
      });
      const data = await resp.json();
      if (!resp.ok) {
        if (listError) {
          listError.textContent = data.error || 'Falha ao criar base.';
          listError.style.display = 'block';
        }
      } else {
        inputName.value = '';
        fetchDatabases();
      }
    } catch (err) {
      if (listError) {
        listError.textContent = 'Erro na requisição: ' + err.message;
        listError.style.display = 'block';
      }
      console.error(err);
    }
  });
}

// Execução de comandos SQL (botão <button id="execSqlBtn">)
function setupSqlExecution() {
  const btn = document.getElementById('execSqlBtn');
  if (!btn) return;

  btn.addEventListener('click', async () => {
    const selectElem = document.getElementById('dbSelect');
    const dbname     = selectElem.value;
    const sql        = document.getElementById('sqlInput').value.trim();
    const errDiv     = document.getElementById('sqlError');
    const resDiv     = document.getElementById('sqlResult');

    if (errDiv) errDiv.style.display = 'none';
    if (resDiv) resDiv.textContent = "";

    if (!dbname) {
      if (errDiv) {
        errDiv.textContent = 'Selecione uma base válida.';
        errDiv.style.display = 'block';
      }
      return;
    }
    if (!sql) {
      if (errDiv) {
        errDiv.textContent = 'Digite um comando SQL.';
        errDiv.style.display = 'block';
      }
      return;
    }

    try {
      const resp = await fetch('/db-query', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dbname, sql })
      });
      const data = await resp.json();

      if (!resp.ok) {
        if (errDiv) {
          errDiv.textContent = data.error || 'Erro desconhecido ao executar SQL.';
          errDiv.style.display = 'block';
        }
      } else {
        if (data.rows) {
          if (data.rows.length === 0) {
            resDiv.textContent = '< nenhuma linha retornada >';
          } else {
            const cols = Object.keys(data.rows[0]);
            let txt = cols.join('\t') + '\n';
            data.rows.forEach(row => {
              txt += cols.map(c => row[c]).join('\t') + '\n';
            });
            resDiv.textContent = txt;
          }
        } else {
          let msg = data.message || 'Comando executado.';
          if (data.rowcount != null) msg += `  Linhas afetadas: ${data.rowcount}`;
          resDiv.textContent = msg;
        }
      }
    } catch (err) {
      if (errDiv) {
        errDiv.textContent = 'Falha na requisição: ' + err.message;
        errDiv.style.display = 'block';
      }
      console.error("Erro ao executar SQL:", err);
    }
  });
}

// ===== Configuração inicial ao carregar o DOM =====
document.addEventListener("DOMContentLoaded", () => {
  // Se estiver na página index.html (login/registo)
  const loginBtn    = document.getElementById("loginBtn");
  const registerBtn = document.getElementById("registerBtn");
  if (loginBtn)    loginBtn.addEventListener("click", login);
  if (registerBtn) registerBtn.addEventListener("click", register);

  // Se estiver na dashboard
  const username = localStorage.getItem("loggedUser");
  if (username) {
    // Exibe username em <strong id="loggedUsername"> (se existir)
    const usernameSpan = document.getElementById("loggedUsername");
    if (usernameSpan) {
      usernameSpan.textContent = username;
    }

    // Carregar lista de arquivos, uso de armazenamento e jobs
    listFiles();
    updateUsage();
    loadJobs();

    // Buscar lista de bancos de dados
    fetchDatabases();
  }

  // Upload de arquivo (<form id="uploadForm">)
  const uploadForm = document.getElementById("uploadForm");
  if (uploadForm) {
    uploadForm.addEventListener("submit", e => {
      e.preventDefault();
      uploadFile();
    });
  }

  // Submissão de job de script (<form id="jobForm">)
  setupJobForm();

  // Submissão de criação de DB (<form id="createDbForm">)
  setupCreateDbForm();

  // Execução de SQL (botão #execSqlBtn)
  setupSqlExecution();
});
