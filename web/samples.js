// Editable examples for Add knowledge. Never saved automatically.
const knowledgeSamples = {
  note: {
    title: "DBMS revision: keys and normalization",
    tags: "sample, dbms, revision",
    body: "A database management system (DBMS) helps store, retrieve and manage structured data.\n\nPrimary key: uniquely identifies each row in a table.\nForeign key: references a key in another table to link related records.\nNormalization: organizes tables to reduce redundant data and update anomalies.\n\nExample: store student details in Students and course details in Courses. An Enrollments table links students to courses.\n\nRevision question: Why should a course name be stored in Courses instead of repeated in every enrollment?",
  },
  youtube: {
    title: "Introduction to Database Management Systems (DBMS)",
    url: "https://youtu.be/6Iu45VZGQDk?si=jBAUU_BK2tu4kmG8",
    tags: "sample, dbms, lecture",
    body: "Watch this introduction to DBMS. Add your own notes about databases, tables, keys and their uses.\n\nThis is a sample learning prompt, not a transcript or summary of the video.",
    transcript: "",
  },
  web: {
    title: "SQLite: foreign key documentation",
    url: "https://www.sqlite.org/foreignkeys.html",
    tags: "sample, dbms, sqlite",
    body: "Reading prompt: learn how foreign keys connect related tables and help preserve referential integrity.\n\nTry relating Students and Enrollments using student_id. This prompt is original sample text, not an excerpt from the linked page.",
  },
  chat: {
    title: "Example conversation: database normalization",
    tags: "sample, dbms, conversation",
    body: "Sample conversation for learning (not a saved ARIA response).\n\nStudent: Why do we normalize a database?\nTutor: To reduce repeated data and avoid insertion, update and deletion anomalies.\n\nStudent: Can you give a college example?\nTutor: Keep each course name in a Courses table. Enrollments can reference course_id instead of repeating the name for every student.\n\nStudent: How do primary and foreign keys help?\nTutor: A primary key uniquely identifies a row. A foreign key links a row to a related record in another table.\n\nStudent: What should I revise next?\nTutor: Practice identifying keys and splitting a table into related tables.",
  },
  file: {
    title: "DBMS sample document: relational databases",
    tags: "sample, dbms, document",
    body: "A bundled text document for trying file upload, text extraction and search.",
    filename: "dbms-sample-notes.txt",
    fileText:
      "DBMS SAMPLE STUDY NOTES\n\nA relational database organizes data into tables of rows and columns.\n\nStudents(student_id, name)\nCourses(course_id, course_name)\nEnrollments(student_id, course_id)\n\nPrimary keys uniquely identify rows. Foreign keys connect related records.\nNormalization reduces redundant data and helps prevent update anomalies.\n\nACID transactions\nAtomicity: all operations in a transaction succeed together or are rolled back.\nConsistency: transactions preserve defined database rules.\nIsolation: concurrent transactions are controlled according to an isolation level.\nDurability: committed changes persist.\n\nPractice: Explain why course_name belongs in Courses rather than Enrollments.\n",
  },
  code: {
    title: "SQL example: students and enrollments",
    tags: "sample, dbms, sql",
    body: "-- SQLite example: primary keys, foreign keys and a JOIN\nPRAGMA foreign_keys = ON;\n\nCREATE TABLE students (\n  student_id INTEGER PRIMARY KEY,\n  name TEXT NOT NULL\n);\nCREATE TABLE courses (\n  course_id INTEGER PRIMARY KEY,\n  course_name TEXT NOT NULL\n);\nCREATE TABLE enrollments (\n  student_id INTEGER REFERENCES students(student_id),\n  course_id INTEGER REFERENCES courses(course_id),\n  PRIMARY KEY (student_id, course_id)\n);\n\nINSERT INTO students VALUES (1, 'Asha');\nINSERT INTO courses VALUES (101, 'DBMS');\nINSERT INTO enrollments VALUES (1, 101);\n\nSELECT s.name, c.course_name\nFROM enrollments e\nJOIN students s ON s.student_id = e.student_id\nJOIN courses c ON c.course_id = e.course_id;\n\n-- Expected result: Asha | DBMS",
  },
};
function fillKnowledgeSample() {
  const form = document.querySelector("#capture-form");
  if (!form || form.dataset.id) return;
  const sample = knowledgeSamples[form.dataset.kind];
  if (!sample) return;
  const fields = ["title", "tags", "body", "url", "transcript"];
  const hasDraft = fields.some((name) => form.elements.namedItem(name)?.value.trim()) || state.file;
  if (
    hasDraft &&
    !confirm("Replace this draft with the sample? Your collection selection will stay the same.")
  )
    return;
  for (const name of fields) {
    const field = form.elements.namedItem(name);
    if (field) field.value = sample[name] || "";
  }
  if (sample.fileText) {
    state.file = new File([sample.fileText], sample.filename, {
      type: "text/plain",
    });
    const input = form.querySelector("#capture-file");
    input.value = "";
    // Show the actual attachment in the picker where supported.
    try {
      const transfer = new DataTransfer();
      transfer.items.add(state.file);
      input.files = transfer.files;
    } catch (_) {
      /* state.file remains the upload source. */
    }
    form.querySelector("#sample-file-status").textContent = "Sample attached: " + sample.filename;
  }
  form.querySelector("[name=title]").focus();
  toast("Sample filled. Review or edit it, then save to knowledge.");
}
