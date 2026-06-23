/** Chat + Video Generation frontend controller. */

// ---------- Common elements ----------
const tabChat = document.getElementById("tabChat");
const tabVideoGen = document.getElementById("tabVideoGen");
const chatPanel = document.getElementById("chatPanel");
const videoGenPanel = document.getElementById("videoGenPanel");

// ---------- Chat mode elements ----------
const idleVideoUrl = "/avatars/default_base.mp4";
const videoBox = document.getElementById("videoBox");
const transcript = document.getElementById("transcript");
const metrics = document.getElementById("metrics");
const chatStatus = document.getElementById("chatStatus");
const textInput = document.getElementById("textInput");
const voiceSelect = document.getElementById("voiceSelect");
const langSelect = document.getElementById("langSelect");
const sendBtn = document.getElementById("sendBtn");

// ---------- Video generation elements ----------
const videoUpload = document.getElementById("videoUpload");
const uploadBtn = document.getElementById("uploadBtn");
const uploadStatus = document.getElementById("uploadStatus");
const uploadProgress = document.getElementById("uploadProgress");
const uploadProgressBar = uploadProgress.parentElement;
const uploadPreview = document.getElementById("uploadPreview");
const genTextInput = document.getElementById("genTextInput");
const spkSelect = document.getElementById("spkSelect");
const generateBtn = document.getElementById("generateBtn");
const generateStatus = document.getElementById("generateStatus");
const generateProgress = document.getElementById("generateProgress");
const generateProgressBar = generateProgress.parentElement;
const resultSection = document.getElementById("resultSection");
const resultVideo = document.getElementById("resultVideo");
const downloadLink = document.getElementById("downloadLink");

let currentUploadId = null;
let uploadPollTimer = null;
let generatePollTimer = null;
let selectedFile = null;

// ---------- Tab switching ----------
function switchTab(mode) {
  if (mode === "chat") {
    chatPanel.classList.add("active");
    videoGenPanel.classList.remove("active");
    tabChat.classList.add("active");
    tabVideoGen.classList.remove("active");
  } else {
    chatPanel.classList.remove("active");
    videoGenPanel.classList.add("active");
    tabChat.classList.remove("active");
    tabVideoGen.classList.add("active");
  }
}

tabChat.addEventListener("click", () => switchTab("chat"));
tabVideoGen.addEventListener("click", () => switchTab("video-gen"));

// ---------- Chat mode ----------
function resetIdle() {
  videoBox.innerHTML = '';
  const v = document.createElement("video");
  v.id = "idleVideo";
  v.autoplay = true; v.loop = true; v.muted = true; v.playsInline = true;
  v.src = idleVideoUrl;
  v.style.width = "100%"; v.style.height = "100%";
  videoBox.appendChild(v);
  v.play().catch(()=>{});
}
resetIdle();

sendBtn.addEventListener("click", async () => {
  const text = textInput.value.trim();
  if (!text) return;
  sendBtn.disabled = true;
  chatStatus.textContent = "🟡 等待大模型首 token...";
  metrics.textContent = "";
  transcript.innerHTML = "";

  const params = new URLSearchParams({
    text: text,
    voice: voiceSelect.value,
    lang: langSelect.value,
    max_tokens: "128"
  });
  const evtSource = new EventSource("/api/chat?" + params.toString());

  evtSource.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    const ev = msg.event;
    const p = msg.payload || {};
    if (ev === "llm_text") {
      transcript.innerHTML += p.delta || "";
    } else if (ev === "stream_ready") {
      const url = p.webrtc_url;
      videoBox.innerHTML = `<iframe src="${url}" allow="autoplay; fullscreen" style="width:100%;height:100%;border:none;background:#000"></iframe>`;
      metrics.textContent = `首帧延迟: ${p.first_video_latency_ms || '--'} ms | TTS: ${p.tts_latency_ms || '--'} ms`;
      chatStatus.textContent = "🟢 正在播放唇形同步流...";
    } else if (ev === "sentence_stream_done") {
      chatStatus.textContent = "✅ 当前句播放完成";
    } else if (ev === "done") {
      chatStatus.textContent = "✅ 完成";
      evtSource.close();
      sendBtn.disabled = false;
      resetIdle();
    } else if (ev === "error") {
      chatStatus.textContent = "❌ 错误: " + (p.message || "");
      evtSource.close();
      sendBtn.disabled = false;
      resetIdle();
    }
  };

  evtSource.onerror = (e) => {
    chatStatus.textContent = "❌ SSE 连接错误";
    evtSource.close();
    sendBtn.disabled = false;
    resetIdle();
  };
});

// ---------- Voice list for PaddleSpeech ----------
async function loadVoices() {
  try {
    const res = await fetch("/api/voices");
    const data = await res.json();
    const voices = data.paddlespeech || [];
    spkSelect.innerHTML = "";
    if (voices.length === 0) {
      for (let i = 0; i <= 173; i++) {
        const opt = document.createElement("option");
        opt.value = i;
        opt.textContent = `说话人 ${i}`;
        spkSelect.appendChild(opt);
      }
    } else {
      voices.forEach(v => {
        const opt = document.createElement("option");
        opt.value = v.id;
        opt.textContent = v.name || `说话人 ${v.id}`;
        spkSelect.appendChild(opt);
      });
    }
  } catch (e) {
    spkSelect.innerHTML = "";
    for (let i = 0; i <= 173; i++) {
      const opt = document.createElement("option");
      opt.value = i;
      opt.textContent = `说话人 ${i}`;
      spkSelect.appendChild(opt);
    }
  }
}
loadVoices();

// ---------- Video upload ----------
videoUpload.addEventListener("change", () => {
  selectedFile = videoUpload.files[0];
  if (selectedFile) {
    uploadStatus.textContent = `已选择: ${selectedFile.name}`;
    uploadPreview.src = URL.createObjectURL(selectedFile);
    uploadPreview.style.display = "block";
  }
});

uploadBtn.addEventListener("click", () => {
  if (!selectedFile) {
    uploadStatus.textContent = "请先选择视频文件";
    return;
  }
  uploadBtn.disabled = true;
  uploadStatus.textContent = "上传中...";
  uploadProgressBar.classList.add("active");
  uploadProgress.style.width = "0%";

  const form = new FormData();
  form.append("file", selectedFile);

  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/upload");
  xhr.upload.addEventListener("progress", (e) => {
    if (e.lengthComputable) {
      const pct = Math.round((e.loaded / e.total) * 100);
      uploadProgress.style.width = pct + "%";
      uploadStatus.textContent = `上传中 ${pct}%...`;
    }
  });
  xhr.addEventListener("load", () => {
    uploadBtn.disabled = false;
    try {
      const resp = JSON.parse(xhr.responseText);
      if (resp.error) {
        uploadStatus.textContent = "❌ " + resp.error;
        uploadProgressBar.classList.remove("active");
        return;
      }
      currentUploadId = resp.upload_id;
      uploadStatus.textContent = "✅ 上传成功，开始预处理...";
      startUploadPolling(currentUploadId);
    } catch (err) {
      uploadStatus.textContent = "❌ 解析响应失败";
      uploadProgressBar.classList.remove("active");
    }
  });
  xhr.addEventListener("error", () => {
    uploadBtn.disabled = false;
    uploadStatus.textContent = "❌ 上传失败";
    uploadProgressBar.classList.remove("active");
  });
  xhr.send(form);
});

function startUploadPolling(uploadId) {
  if (uploadPollTimer) clearInterval(uploadPollTimer);
  uploadPollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/upload/status/${uploadId}`);
      const data = await res.json();
      if (data.error) {
        uploadStatus.textContent = "❌ " + data.error;
        uploadProgressBar.classList.remove("active");
        clearInterval(uploadPollTimer);
        return;
      }
      uploadStatus.textContent = data.message || data.status;
      uploadProgress.style.width = Math.max(5, Math.min(95, (data.progress || 0) * 100)) + "%";
      if (data.status === "ready") {
        uploadStatus.textContent = "✅ 视频预处理完成，可以生成";
        uploadProgress.style.width = "100%";
        generateBtn.disabled = false;
        generateStatus.textContent = "准备就绪";
        clearInterval(uploadPollTimer);
      } else if (data.status === "error") {
        uploadStatus.textContent = "❌ " + (data.message || "预处理失败");
        uploadProgressBar.classList.remove("active");
        clearInterval(uploadPollTimer);
      }
    } catch (e) {
      uploadStatus.textContent = "❌ 轮询状态失败";
      clearInterval(uploadPollTimer);
    }
  }, 1000);
}

// ---------- Video generation ----------
generateBtn.addEventListener("click", async () => {
  const text = genTextInput.value.trim();
  if (!text) {
    generateStatus.textContent = "请输入文本";
    return;
  }
  if (!currentUploadId) {
    generateStatus.textContent = "请先上传视频";
    return;
  }
  generateBtn.disabled = true;
  generateStatus.textContent = "提交任务中...";
  generateProgressBar.classList.add("active");
  generateProgress.style.width = "5%";
  resultSection.style.display = "none";

  const form = new FormData();
  form.append("upload_id", currentUploadId);
  form.append("text", text);
  form.append("spk_id", spkSelect.value);

  try {
    const res = await fetch("/api/generate", { method: "POST", body: form });
    const data = await res.json();
    if (data.error) {
      generateStatus.textContent = "❌ " + data.error;
      generateBtn.disabled = false;
      return;
    }
    startGeneratePolling(data.job_id);
  } catch (e) {
    generateStatus.textContent = "❌ 提交失败";
    generateBtn.disabled = false;
  }
});

function startGeneratePolling(jobId) {
  if (generatePollTimer) clearInterval(generatePollTimer);
  generatePollTimer = setInterval(async () => {
    try {
      const res = await fetch(`/api/generate/status/${jobId}`);
      const data = await res.json();
      if (data.error) {
        generateStatus.textContent = "❌ " + data.error;
        generateBtn.disabled = false;
        clearInterval(generatePollTimer);
        return;
      }
      generateStatus.textContent = data.message || data.status;
      generateProgress.style.width = Math.max(5, Math.min(95, (data.progress || 0) * 100)) + "%";
      if (data.status === "done") {
        generateStatus.textContent = "✅ 生成完成";
        generateProgress.style.width = "100%";
        resultSection.style.display = "block";
        resultVideo.src = `/api/download/${jobId}`;
        downloadLink.href = `/api/download/${jobId}`;
        generateBtn.disabled = false;
        clearInterval(generatePollTimer);
      } else if (data.status === "error") {
        generateStatus.textContent = "❌ " + (data.message || "生成失败");
        generateBtn.disabled = false;
        clearInterval(generatePollTimer);
      }
    } catch (e) {
      generateStatus.textContent = "❌ 轮询状态失败";
      generateBtn.disabled = false;
      clearInterval(generatePollTimer);
    }
  }, 1000);
}
