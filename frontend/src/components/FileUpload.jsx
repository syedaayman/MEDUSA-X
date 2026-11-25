import { useState } from "react";
import { uploadDocument } from "../services/api.js";

export default function FileUpload() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!file) return;

    setIsUploading(true);
    setError("");
    setResult(null);
    try {
      const response = await uploadDocument(file);
      setResult(response);
    } catch (uploadError) {
      setError(
        uploadError.response?.data?.detail ??
          "Upload failed. Confirm the local API is running and try again.",
      );
    } finally {
      setIsUploading(false);
    }
  }

  function handleFileChange(event) {
    setFile(event.target.files?.[0] ?? null);
    setResult(null);
    setError("");
  }

  return (
    <section className="card upload-card" aria-labelledby="upload-title">
      <div className="card-header">
        <div>
          <h2 id="upload-title">Add a document</h2>
          <p>Extract selectable text from a PDF for review</p>
        </div>
        <span className="status-badge">Local processing</span>
      </div>
      <form onSubmit={handleSubmit}>
        <label className="upload-dropzone" htmlFor="document-file">
          <span>
            <span className="upload-icon" aria-hidden="true">
              ↑
            </span>
            <strong>Choose a PDF to inspect</strong>
            <span>Files are processed in memory and are not saved</span>
          </span>
        </label>
        <input
          accept="application/pdf,.pdf"
          className="file-input"
          id="document-file"
          onChange={handleFileChange}
          type="file"
        />
        <div className="upload-actions">
          <span className="file-name">{file?.name ?? "No file selected"}</span>
          <button className="button" disabled={!file || isUploading} type="submit">
            {isUploading ? "Reading…" : "Read PDF"}
          </button>
        </div>
      </form>
      <p className="notice">
        OCR, clinical extraction, and reconciliation are not active. Uploading does not
        produce clinical findings.
      </p>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="upload-result" role="status">
          <h3>{result.filename}</h3>
          <p>
            {result.message} {result.page_count} page(s) read.
          </p>
          {result.ocr_required_pages.length > 0 && (
            <p>
              OCR placeholder: no selectable text on page(s){" "}
              {result.ocr_required_pages.join(", ")}.
            </p>
          )}
          {result.pages.map((page) => (
            <pre className="extracted-page" key={page.page_number}>
              Page {page.page_number}: {page.text || "No selectable text found."}
            </pre>
          ))}
        </div>
      )}
    </section>
  );
}
