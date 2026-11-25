import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiError, uploadDocuments } from "../services/api.js";
import { asList } from "../lib/format.js";

const MAX_BYTES = 20 * 1024 * 1024;

export default function FileUpload({ defaultPatientId = "", onUploaded }) {
  const navigate = useNavigate();
  const inputRef = useRef(null);
  const [patientId, setPatientId] = useState(defaultPatientId);
  const [displayName, setDisplayName] = useState("");
  const [files, setFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);

  function addFiles(incoming) {
    const accepted = [];
    const rejected = [];
    Array.from(incoming ?? []).forEach((file) => {
      const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
      if (!isPdf) rejected.push(`${file.name}: only PDF files are supported.`);
      else if (file.size > MAX_BYTES) rejected.push(`${file.name}: larger than the 20 MB limit.`);
      else accepted.push(file);
    });
    if (accepted.length) setFiles((current) => [...current, ...accepted]);
    setError(rejected.join(" "));
    setResult(null);
  }

  function removeFile(index) {
    setFiles((current) => current.filter((_, position) => position !== index));
  }

  async function handleSubmit(event) {
    event.preventDefault();
    if (!files.length) {
      setError("Select at least one PDF to upload.");
      return;
    }
    const trimmed = patientId.trim();
    if (!trimmed) {
      setError("A patient identifier is required so documents stay isolated per patient.");
      return;
    }

    setIsUploading(true);
    setError("");
    setResult(null);
    try {
      const response = await uploadDocuments({
        patientId: trimmed,
        displayName: displayName.trim(),
        files,
        startAnalysis: true,
      });
      setResult(response);
      const createdPatient = response?.patient_id ?? trimmed;
      setFiles([]);
      if (onUploaded) onUploaded(createdPatient);
      else navigate(`/patients/${encodeURIComponent(createdPatient)}`);
    } catch (uploadError) {
      setError(apiError(uploadError, "Upload failed. Confirm the API is running."));
    } finally {
      setIsUploading(false);
    }
  }

  const uploadedDocuments = asList(result?.documents);
  const uploadErrors = asList(result?.errors);

  return (
    <section className="card upload-card" aria-labelledby="upload-title">
      <div className="card-header">
        <div>
          <h2 id="upload-title">Add patient documents</h2>
          <p>Multiple PDFs · stored with page-level evidence</p>
        </div>
        <span className="status-badge">Backend processing</span>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="grid-2">
          <label className="field">
            <span className="field-label">Patient identifier</span>
            <input
              className="text-input"
              onChange={(event) => setPatientId(event.target.value)}
              placeholder="e.g. patient-001"
              value={patientId}
            />
          </label>
          <label className="field">
            <span className="field-label">Display name (optional)</span>
            <input
              className="text-input"
              onChange={(event) => setDisplayName(event.target.value)}
              placeholder="e.g. Jordan Ellis"
              value={displayName}
            />
          </label>
        </div>

        <div
          className={`upload-dropzone${isDragging ? " dragging" : ""}`}
          onClick={() => inputRef.current?.click()}
          onDragOver={(event) => {
            event.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(event) => {
            event.preventDefault();
            setIsDragging(false);
            addFiles(event.dataTransfer.files);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
          }}
          role="button"
          tabIndex={0}
        >
          <span>
            <span className="upload-icon" aria-hidden="true">
              ↑
            </span>
            <strong>Drop PDFs here or click to select</strong>
            <span>Discharge summaries, prescriptions, laboratory and diagnostic reports</span>
          </span>
        </div>
        <input
          accept="application/pdf,.pdf"
          className="file-input"
          multiple
          onChange={(event) => addFiles(event.target.files)}
          ref={inputRef}
          type="file"
        />

        {files.length > 0 && (
          <ul className="plain-list">
            {files.map((file, index) => (
              <li className="row-between" key={`${file.name}-${index}`}>
                <span className="file-name">
                  {file.name} · {(file.size / 1024).toFixed(0)} KB
                </span>
                <button className="link-button" onClick={() => removeFile(index)} type="button">
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="upload-actions">
          <span className="file-name">
            {files.length ? `${files.length} file(s) ready` : "No files selected"}
          </span>
          <button className="button" disabled={isUploading || !files.length} type="submit">
            {isUploading ? "Uploading & starting analysis…" : "Upload and analyse"}
          </button>
        </div>
      </form>

      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="upload-result" role="status">
          <h3>Upload accepted</h3>
          <p>
            {uploadedDocuments.length} document(s) stored for patient{" "}
            <strong>{result.patient_id ?? patientId}</strong>.
            {result.analysis_run_id ? ` Analysis run ${result.analysis_run_id} started.` : ""}
          </p>
          {uploadedDocuments.map((document) => (
            <p key={document.id ?? document.document_id}>
              {(document.filename ?? "document")} · {document.page_count ?? "?"} page(s) ·{" "}
              {document.processing_status ?? "STORED"}
              {document.duplicate ? " · duplicate of an existing upload" : ""}
            </p>
          ))}
          {uploadErrors.length > 0 && (
            <p className="notice error">
              {uploadErrors
                .map((item) => `${item.filename ?? "file"}: ${item.error ?? "failed"}`)
                .join("; ")}
            </p>
          )}
        </div>
      )}
    </section>
  );
}
