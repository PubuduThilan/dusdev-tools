const MAX_FILE_SIZE = 25 * 1024 * 1024;

function setStatus(form, message, type = "") {
  const status = form.querySelector("[data-status]") || form.querySelector(".form-status");
  if (!status) return;
  status.textContent = message;
  status.classList.remove("error", "success");
  if (type) status.classList.add(type);
}

function clearResult(form) {
  const resultBox = form.querySelector("[data-result]");
  if (resultBox) resultBox.replaceChildren();
}

function showDownload(form, data) {
  const resultBox = form.querySelector("[data-result]");
  if (!resultBox) return;

  const wrapper = document.createElement("div");
  wrapper.className = "download-card";

  const fileLabel = document.createElement("strong");
  fileLabel.textContent = data.filename || "Converted file";

  const link = document.createElement("a");
  link.className = "btn btn-primary";
  link.href = data.download_url;
  link.textContent = "Download";

  wrapper.append(fileLabel, link);
  resultBox.replaceChildren(wrapper);
}

function bindUploadForms() {
  document.querySelectorAll(".ajax-upload-form").forEach((form) => {
    const fileInput = form.querySelector('input[type="file"]');
    const submitButton = form.querySelector('button[type="submit"]');
    const fileNameLabel = form.querySelector("[data-file-name]");
    const dropZone = fileInput ? fileInput.closest(".file-drop") : null;

    if (fileInput && fileNameLabel) {
      fileInput.addEventListener("change", () => {
        const file = fileInput.files[0];
        clearResult(form);
        if (!file) {
          fileNameLabel.textContent = "No file selected";
          setStatus(form, "");
          return;
        }

        fileNameLabel.textContent = file.name;
        if (file.size > MAX_FILE_SIZE) {
          setStatus(form, "Files must be 25MB or smaller.", "error");
        } else {
          setStatus(form, "");
        }
      });
    }

    if (dropZone && fileInput) {
      ["dragenter", "dragover"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropZone.classList.add("is-dragover");
        });
      });

      ["dragleave", "drop"].forEach((eventName) => {
        dropZone.addEventListener(eventName, (event) => {
          event.preventDefault();
          dropZone.classList.remove("is-dragover");
        });
      });

      dropZone.addEventListener("drop", (event) => {
        const droppedFile = event.dataTransfer.files[0];
        if (!droppedFile || typeof DataTransfer === "undefined") return;

        const transfer = new DataTransfer();
        transfer.items.add(droppedFile);
        fileInput.files = transfer.files;
        fileInput.dispatchEvent(new Event("change", { bubbles: true }));
      });
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      clearResult(form);

      const file = fileInput ? fileInput.files[0] : null;
      if (!file) {
        setStatus(form, "Please choose a file first.", "error");
        return;
      }
      if (file.size > MAX_FILE_SIZE) {
        setStatus(form, "Files must be 25MB or smaller.", "error");
        return;
      }

      form.classList.add("is-loading");
      if (submitButton) submitButton.disabled = true;
      setStatus(form, "Processing your file...");

      try {
        const response = await fetch(form.action, {
          method: "POST",
          body: new FormData(form),
        });
        const data = await response.json();

        if (!response.ok) {
          throw new Error(data.error || "Something went wrong. Please try again.");
        }

        setStatus(form, data.message || "Conversion complete.", "success");
        showDownload(form, data);
      } catch (error) {
        setStatus(form, error.message, "error");
      } finally {
        form.classList.remove("is-loading");
        if (submitButton) submitButton.disabled = false;
      }
    });
  });
}

function bindNavigation() {
  const toggle = document.querySelector(".nav-toggle");
  const menu = document.querySelector(".nav-links");
  if (!toggle || !menu) return;

  toggle.addEventListener("click", () => {
    const isOpen = menu.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(isOpen));
    toggle.setAttribute("aria-label", isOpen ? "Close menu" : "Open menu");
  });
}

function bindJsonFormatter() {
  const input = document.querySelector("#json-input");
  const formatButton = document.querySelector("#format-json");
  const minifyButton = document.querySelector("#minify-json");
  const status = document.querySelector("#json-status");
  if (!input || !formatButton || !minifyButton || !status) return;

  const handleJson = (space) => {
    try {
      const parsed = JSON.parse(input.value);
      input.value = JSON.stringify(parsed, null, space);
      status.textContent = space ? "JSON formatted." : "JSON minified.";
      status.className = "form-status success";
    } catch (error) {
      status.textContent = "Invalid JSON. Check commas, quotes, and brackets.";
      status.className = "form-status error";
    }
  };

  formatButton.addEventListener("click", () => handleJson(2));
  minifyButton.addEventListener("click", () => handleJson(0));
}

function bindBase64Tools() {
  const input = document.querySelector("#base64-input");
  const output = document.querySelector("#base64-output");
  const encodeButton = document.querySelector("#encode-base64");
  const decodeButton = document.querySelector("#decode-base64");
  const status = document.querySelector("#base64-status");
  if (!input || !output || !encodeButton || !decodeButton || !status) return;

  encodeButton.addEventListener("click", () => {
    output.value = btoa(unescape(encodeURIComponent(input.value)));
    status.textContent = "Encoded to Base64.";
    status.className = "form-status success";
  });

  decodeButton.addEventListener("click", () => {
    try {
      output.value = decodeURIComponent(escape(atob(input.value)));
      status.textContent = "Decoded from Base64.";
      status.className = "form-status success";
    } catch (error) {
      status.textContent = "Invalid Base64 input.";
      status.className = "form-status error";
    }
  });
}

function bindPasswordGenerator() {
  const lengthInput = document.querySelector("#password-length");
  const uppercaseInput = document.querySelector("#include-uppercase");
  const numbersInput = document.querySelector("#include-numbers");
  const symbolsInput = document.querySelector("#include-symbols");
  const generateButton = document.querySelector("#generate-password");
  const output = document.querySelector("#password-output");
  if (!lengthInput || !generateButton || !output) return;

  generateButton.addEventListener("click", () => {
    const lower = "abcdefghijklmnopqrstuvwxyz";
    const upper = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";
    const numbers = "0123456789";
    const symbols = "!@#$%^&*_-+=?";
    let characters = lower;

    if (uppercaseInput.checked) characters += upper;
    if (numbersInput.checked) characters += numbers;
    if (symbolsInput.checked) characters += symbols;

    const length = Math.min(64, Math.max(8, Number(lengthInput.value) || 18));
    const bytes = new Uint32Array(length);
    window.crypto.getRandomValues(bytes);

    output.value = Array.from(bytes, (value) => characters[value % characters.length]).join("");
  });
}

document.addEventListener("DOMContentLoaded", () => {
  bindNavigation();
  bindUploadForms();
  bindJsonFormatter();
  bindBase64Tools();
  bindPasswordGenerator();
});
