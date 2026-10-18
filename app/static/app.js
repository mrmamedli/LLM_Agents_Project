"use strict";

const API = "/api";

const FILE_STATUS = {
  uploaded: "Загружен",
  processing: "Обработка…",
  done: "Готово",
  error: "Ошибка",
};
const ACTIVE_STATUSES = new Set(["uploaded", "processing"]);
const DOC_TYPES = {
  lecture: "Лекция",
  assignment: "Задание",
  rules: "Правила курса",
  other: "Другое",
};
const DEADLINE_STATUS = {
  confirmed: "Дата подтверждена",
  needs_confirmation: "Требует подтверждения",
  undefined: "Дата не определена",
};
const POLL_INTERVAL_MS = 2000;

const state = {
  subjects: [],
  view: null, // subject id (number), "calendar" or null
  files: [],
  selectedFileId: null,
  card: null,
  calendarFilter: "",
  pollTimer: null,
};

const $ = (selector) => document.querySelector(selector);

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") el.className = value;
    else if (key.startsWith("on")) el.addEventListener(key.slice(2), value);
    else if (value === true) el.setAttribute(key, "");
    else if (value !== false && value != null) el.setAttribute(key, value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

let toastTimer;
function showError(message) {
  const toast = $("#toast");
  toast.textContent = message;
  toast.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 5000);
}

async function api(path, options = {}) {
  const response = await fetch(API + path, options);
  const text = await response.text();
  if (!response.ok) {
    let detail = response.statusText;
    try {
      detail = JSON.parse(text).detail || detail;
    } catch {
      // body is not JSON, keep the status text
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return text ? JSON.parse(text) : null;
}

function jsonRequest(method, body) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

// ---------- dates ----------

function todayKey() {
  return new Date().toLocaleDateString("sv-SE");
}

function dayKey(due) {
  return due.slice(0, 10);
}

function formatDay(key, options) {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString("ru-RU", options);
}

function formatDue(due) {
  const day = formatDay(dayKey(due), { day: "numeric", month: "long", year: "numeric" });
  return due.includes("T") ? `${day}, ${due.slice(11, 16)}` : day;
}

function pill(label, kind) {
  return h("span", { class: `pill ${kind}` }, label);
}

// ---------- rendering: shell ----------

function render() {
  renderTabs();
  if (state.view === "calendar") renderCalendar();
  else if (typeof state.view === "number") renderSubject();
  else {
    $("#view").replaceChildren(
      h("p", { class: "empty" }, "Создайте первый предмет, чтобы начать загружать материалы."),
    );
  }
}

function renderTabs() {
  $("#tabs").replaceChildren(
    ...state.subjects.map((subject) =>
      h(
        "button",
        {
          class: "tab" + (state.view === subject.id ? " active" : ""),
          onclick: () => openSubject(subject.id),
        },
        subject.name,
      ),
    ),
    h(
      "button",
      { class: "tab" + (state.view === "calendar" ? " active" : ""), onclick: openCalendar },
      "Календарь",
    ),
  );
}

// ---------- subjects ----------

async function openSubject(id) {
  clearTimeout(state.pollTimer);
  state.view = id;
  state.files = [];
  state.selectedFileId = null;
  state.card = null;
  render();
  await loadFiles();
  renderFiles();
  schedulePoll();
}

async function addSubject(event) {
  event.preventDefault();
  const input = $("#subject-name");
  const name = input.value.trim();
  if (!name) return;
  try {
    const subject = await api("/subjects", jsonRequest("POST", { name }));
    state.subjects.push(subject);
    input.value = "";
    await openSubject(subject.id);
  } catch (error) {
    showError(error.message);
  }
}

async function removeSubject(subject) {
  if (!confirm(`Удалить предмет «${subject.name}» вместе со всеми файлами?`)) return;
  try {
    await api(`/subjects/${subject.id}`, { method: "DELETE" });
    state.subjects = state.subjects.filter((s) => s.id !== subject.id);
    if (state.subjects.length) await openSubject(state.subjects[0].id);
    else {
      clearTimeout(state.pollTimer);
      state.view = null;
      render();
    }
  } catch (error) {
    showError(error.message);
  }
}

function renderSubject() {
  const subject = state.subjects.find((s) => s.id === state.view);
  $("#view").replaceChildren(
    h(
      "div",
      { class: "subject-head" },
      h("h2", {}, subject.name),
      h("button", { class: "btn danger", onclick: () => removeSubject(subject) }, "Удалить предмет"),
    ),
    uploadZone(),
    h(
      "div",
      { class: "split" },
      h("section", { class: "panel", id: "files-panel" }),
      h("section", { class: "panel", id: "card-panel" }),
    ),
  );
  renderFiles();
  renderCard();
}

// ---------- files ----------

async function loadFiles() {
  const id = state.view;
  try {
    const files = await api(`/subjects/${id}/files`);
    if (state.view === id) state.files = files.sort((a, b) => b.id - a.id);
  } catch (error) {
    showError(error.message);
  }
}

function uploadZone() {
  const input = h("input", {
    type: "file",
    accept: ".pdf,application/pdf",
    multiple: true,
    onchange: () => {
      uploadFiles([...input.files]);
      input.value = "";
    },
  });
  const zone = h(
    "label",
    { class: "dropzone" },
    input,
    h("strong", {}, "Перетащите PDF сюда или нажмите, чтобы выбрать"),
    h("span", { class: "muted" }, "В MVP поддерживаются только PDF с текстовым слоем"),
  );
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragging");
  });
  zone.addEventListener("dragleave", () => zone.classList.remove("dragging"));
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragging");
    uploadFiles([...event.dataTransfer.files]);
  });
  return zone;
}

async function uploadFiles(files) {
  const subjectId = state.view;
  let last = null;
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      showError(`«${file.name}» не PDF, файл пропущен`);
      continue;
    }
    const body = new FormData();
    body.append("file", file);
    try {
      last = await api(`/subjects/${subjectId}/files`, { method: "POST", body });
    } catch (error) {
      showError(`${file.name}: ${error.message}`);
    }
  }
  if (!last || state.view !== subjectId) return;
  await loadFiles();
  await selectFile(last.id);
}

function renderFiles() {
  const panel = $("#files-panel");
  if (!panel) return;
  const body = state.files.length
    ? h(
        "ul",
        { class: "file-list" },
        state.files.map((file) =>
          h(
            "li",
            {},
            h(
              "button",
              {
                class: "file-item" + (file.id === state.selectedFileId ? " selected" : ""),
                onclick: () => selectFile(file.id),
              },
              h("span", { class: "file-name" }, file.filename),
              h(
                "span",
                { class: "badges" },
                pill(FILE_STATUS[file.status] ?? file.status, file.status),
                file.doc_type ? pill(DOC_TYPES[file.doc_type] ?? file.doc_type, "type") : null,
              ),
            ),
          ),
        ),
      )
    : h("p", { class: "empty" }, "В этом предмете пока нет файлов.");
  panel.replaceChildren(h("h3", {}, "Файлы"), body);
}

async function selectFile(id) {
  state.selectedFileId = id;
  state.card = null;
  renderFiles();
  renderCard();
  await loadCard();
  renderCard();
  schedulePoll();
}

async function openFile(subjectId, fileId) {
  if (state.view !== subjectId) await openSubject(subjectId);
  await selectFile(fileId);
}

async function loadCard() {
  const id = state.selectedFileId;
  if (id == null) return;
  try {
    const card = await api(`/files/${id}`);
    if (state.selectedFileId === id) state.card = card;
  } catch (error) {
    showError(error.message);
  }
}

async function reprocess(fileId) {
  try {
    await api(`/files/${fileId}/reprocess`, { method: "POST" });
    await loadFiles();
    await loadCard();
    renderFiles();
    renderCard();
    schedulePoll();
  } catch (error) {
    showError(error.message);
  }
}

// ---------- polling ----------

function schedulePoll() {
  clearTimeout(state.pollTimer);
  if (state.files.some((file) => ACTIVE_STATUSES.has(file.status))) {
    state.pollTimer = setTimeout(poll, POLL_INTERVAL_MS);
  }
}

async function poll() {
  const viewId = state.view;
  if (typeof viewId !== "number") return;
  const selected = state.files.find((file) => file.id === state.selectedFileId);
  const selectedWasActive = Boolean(selected) && ACTIVE_STATUSES.has(selected.status);

  await loadFiles();
  if (state.view !== viewId) return;
  if (selectedWasActive) await loadCard();
  if (state.view !== viewId) return;

  renderFiles();
  if (selectedWasActive) renderCard();
  schedulePoll();
}

// ---------- file card ----------

function renderCard() {
  const panel = $("#card-panel");
  if (!panel) return;
  const card = state.card;
  if (!card) {
    const text =
      state.selectedFileId == null
        ? "Выберите файл слева, чтобы увидеть конспект и дедлайны."
        : "Загружаю…";
    panel.replaceChildren(h("p", { class: "empty" }, text));
    return;
  }

  const { file, summary, deadlines } = card;
  const active = ACTIVE_STATUSES.has(file.status);
  const parts = [
    h(
      "div",
      { class: "card-head" },
      h("h3", {}, file.filename),
      h(
        "div",
        { class: "badges" },
        file.doc_type ? pill(DOC_TYPES[file.doc_type] ?? file.doc_type, "type") : null,
        pill(FILE_STATUS[file.status] ?? file.status, file.status),
      ),
      active
        ? null
        : h("button", { class: "btn", onclick: () => reprocess(file.id) }, "Обработать заново"),
    ),
  ];

  if (active) {
    parts.push(h("p", { class: "progress" }, h("span", { class: "spinner" }), "Агент читает файл…"));
  }
  if (file.status === "error") {
    parts.push(h("p", { class: "error-box" }, file.error || "Не удалось обработать файл."));
  }
  if (summary) {
    parts.push(
      h(
        "div",
        { class: "section" },
        h("h4", {}, "Конспект"),
        h("p", { class: "summary" }, summary.text),
        summary.key_terms.length
          ? h("div", { class: "terms" }, summary.key_terms.map((term) => pill(term, "type")))
          : null,
      ),
    );
  }
  if (file.status === "done") {
    parts.push(
      h(
        "div",
        { class: "section" },
        h("h4", {}, "Дедлайны и требования"),
        deadlines.length
          ? deadlines.map((d) => deadlineItem(d, onDeadlineSaved))
          : h("p", { class: "muted" }, "В этом документе дедлайнов не найдено."),
      ),
    );
  }
  panel.replaceChildren(...parts);
}

async function onDeadlineSaved() {
  await loadCard();
  renderCard();
}

// ---------- deadlines ----------

function deadlineItem(deadline, onSaved, { withSubject = false } = {}) {
  const subject = state.subjects.find((s) => s.id === deadline.subject_id);
  return h(
    "article",
    { class: "deadline" },
    h(
      "div",
      { class: "deadline-head" },
      h("h4", {}, deadline.title),
      deadline.due_date ? h("span", { class: "due" }, formatDue(deadline.due_date)) : null,
      pill(DEADLINE_STATUS[deadline.status] ?? deadline.status, deadline.status),
    ),
    withSubject && subject ? h("p", { class: "muted" }, subject.name) : null,
    deadline.date_note ? h("p", { class: "note" }, `В документе: «${deadline.date_note}»`) : null,
    deadline.requirements.length
      ? h("ul", { class: "requirements" }, deadline.requirements.map((req) => h("li", {}, req)))
      : null,
    h("p", { class: "source" }, `Источник: стр. ${deadline.source_page}`),
    deadline.source_quote ? h("blockquote", {}, deadline.source_quote) : null,
    deadline.related_files.length
      ? h(
          "p",
          { class: "related" },
          "Пригодятся: ",
          deadline.related_files.flatMap((file, index) => [
            index ? ", " : null,
            h(
              "button",
              { class: "link", onclick: () => openFile(file.subject_id, file.id) },
              file.filename,
            ),
          ]),
        )
      : null,
    withSubject
      ? h(
          "p",
          {},
          h(
            "button",
            { class: "link", onclick: () => openFile(deadline.subject_id, deadline.file_id) },
            "Открыть материал",
          ),
        )
      : null,
    dateEditor(deadline, onSaved),
  );
}

function dateEditor(deadline, onSaved) {
  const due = deadline.due_date;
  const dateInput = h("input", { type: "date", value: due ? dayKey(due) : "" });
  const timeInput = h("input", {
    type: "time",
    value: due && due.includes("T") ? due.slice(11, 16) : "",
  });

  async function save(dueDate) {
    try {
      await api(
        `/deadlines/${deadline.id}`,
        jsonRequest("PATCH", {
          due_date: dueDate,
          status: dueDate ? "confirmed" : "undefined",
        }),
      );
      await onSaved();
    } catch (error) {
      showError(error.message);
    }
  }

  return h(
    "details",
    { class: "editor" },
    h("summary", {}, "Изменить дату"),
    h(
      "form",
      {
        class: "editor-form",
        onsubmit: (event) => {
          event.preventDefault();
          if (!dateInput.value) {
            showError("Укажите дату");
            return;
          }
          save(dateInput.value + (timeInput.value ? `T${timeInput.value}` : ""));
        },
      },
      dateInput,
      timeInput,
      h("button", { class: "btn primary", type: "submit" }, "Сохранить"),
      h("button", { class: "btn", type: "button", onclick: () => save(null) }, "Очистить дату"),
    ),
  );
}

// ---------- calendar ----------

async function openCalendar() {
  clearTimeout(state.pollTimer);
  state.view = "calendar";
  render();
}

function renderCalendar() {
  const filter = state.calendarFilter;
  const select = h(
    "select",
    {
      onchange: (event) => {
        state.calendarFilter = event.target.value;
        renderCalendar();
      },
    },
    h("option", { value: "" }, "Все предметы"),
    state.subjects.map((subject) =>
      h("option", { value: subject.id, selected: String(subject.id) === filter }, subject.name),
    ),
  );
  const exportUrl = `${API}/calendar.ics${filter ? `?subject_id=${filter}` : ""}`;

  $("#view").replaceChildren(
    h(
      "div",
      { class: "subject-head" },
      h("h2", {}, "Календарь дедлайнов"),
      h(
        "div",
        { class: "head-actions" },
        select,
        h("a", { class: "btn primary", href: exportUrl, download: "studyhub.ics" }, "Экспорт в .ics"),
      ),
    ),
    h("div", { id: "calendar-list" }),
  );
  refreshCalendar();
}

async function refreshCalendar() {
  try {
    const query = state.calendarFilter ? `?subject_id=${state.calendarFilter}` : "";
    const deadlines = await api(`/deadlines${query}`);
    const box = $("#calendar-list");
    if (state.view !== "calendar" || !box) return;
    box.replaceChildren(...calendarSections(deadlines));
  } catch (error) {
    showError(error.message);
  }
}

function calendarSections(deadlines) {
  if (!deadlines.length) {
    return [
      h(
        "p",
        { class: "empty" },
        "Дедлайнов пока нет. Загрузите задания или правила курса, и они появятся здесь.",
      ),
    ];
  }

  const dated = deadlines
    .filter((d) => d.due_date)
    .sort((a, b) => a.due_date.localeCompare(b.due_date));
  const undated = deadlines.filter((d) => !d.due_date);

  const groups = new Map();
  for (const deadline of dated) {
    const key = dayKey(deadline.due_date);
    groups.set(key, [...(groups.get(key) ?? []), deadline]);
  }

  const today = todayKey();
  const sections = [...groups].map(([key, items]) =>
    h(
      "section",
      { class: "day" + (key < today ? " overdue" : key === today ? " today" : "") },
      h(
        "h3",
        {},
        formatDay(key, { weekday: "long", day: "numeric", month: "long", year: "numeric" }),
        key < today ? pill("Просрочено", "error") : null,
        key === today ? pill("Сегодня", "today") : null,
      ),
      items.map((d) => deadlineItem(d, refreshCalendar, { withSubject: true })),
    ),
  );

  if (undated.length) {
    sections.push(
      h(
        "section",
        { class: "day undated" },
        h("h3", {}, "Дата не определена"),
        h(
          "p",
          { class: "muted" },
          "В документах нет точной даты. Уточните её и впишите вручную.",
        ),
        undated.map((d) => deadlineItem(d, refreshCalendar, { withSubject: true })),
      ),
    );
  }
  return sections;
}

// ---------- start ----------

async function init() {
  $("#add-subject").addEventListener("submit", addSubject);
  try {
    state.subjects = await api("/subjects");
  } catch (error) {
    showError(error.message);
  }
  if (state.subjects.length) await openSubject(state.subjects[0].id);
  else render();
}

init();
