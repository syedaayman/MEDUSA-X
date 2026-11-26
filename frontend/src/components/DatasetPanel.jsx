import { useCallback, useEffect, useState } from "react";
import {
  apiError,
  evaluateDataset,
  getDatasetStatus,
  importDataset,
  listDatasets,
} from "../services/api.js";
import { asList, fmtDateTime, statusTone } from "../lib/format.js";

function JsonBlock({ value }) {
  if (!value) return null;
  return <pre className="json-block">{JSON.stringify(value, null, 2)}</pre>;
}

export default function DatasetPanel() {
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [reports, setReports] = useState({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listDatasets();
      setDatasets(asList(data, "datasets"));
      setError("");
    } catch (loadError) {
      setError(apiError(loadError, "Could not load dataset status."));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function run(name, action) {
    setBusy(`${name}:${action}`);
    try {
      const payload =
        action === "import"
          ? await importDataset(name, 25)
          : action === "evaluate"
            ? await evaluateDataset(name, undefined, 20)
            : await getDatasetStatus(name);
      setReports((current) => ({ ...current, [name]: payload }));
      await load();
    } catch (actionError) {
      setReports((current) => ({
        ...current,
        [name]: { error: apiError(actionError, `${action} failed`) },
      }));
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="card overview-card" aria-labelledby="datasets-title">
      <div className="card-header">
        <div>
          <h2 id="datasets-title">Dataset evaluation</h2>
          <p>Synthea longitudinal records and EkaCare evaluation sets — kept separate from uploads</p>
        </div>
        <span className="pill idle">isolated</span>
      </div>

      {loading && <p className="empty-state">Loading dataset registry…</p>}
      {error && <p className="notice error">{error}</p>}

      {!loading && datasets.length === 0 && (
        <p className="empty-state">
          No dataset sources registered. Place downloaded Synthea or EkaCare files under
          sample_data/datasets/ and reload the API.
        </p>
      )}

      <div className="dataset-grid">
        {datasets.map((dataset) => {
          const name = dataset.name ?? dataset.id;
          const status = dataset.import_status ?? "NOT_IMPORTED";
          return (
            <article className="dataset-card" key={name}>
              <div className="row-between">
                <div>
                  <h3>{dataset.title ?? name}</h3>
                  <p className="muted small">{dataset.dataset_type ?? "dataset"}</p>
                </div>
                <span className={`pill ${statusTone(status)}`}>{status}</span>
              </div>

              {dataset.description && <p className="muted small">{dataset.description}</p>}
              <p className="muted small">
                {dataset.source_url ? (
                  <a href={dataset.source_url} rel="noreferrer" target="_blank">
                    {dataset.source_url}
                  </a>
                ) : (
                  "No source URL recorded"
                )}
                {dataset.licence ? ` · ${dataset.licence}` : ""}
                {dataset.imported_at ? ` · imported ${fmtDateTime(dataset.imported_at)}` : ""}
              </p>

              <div className="tag-row">
                <button
                  className="button button-secondary"
                  disabled={busy === `${name}:import`}
                  onClick={() => run(name, "import")}
                  type="button"
                >
                  {busy === `${name}:import` ? "Importing…" : "Import sample (25)"}
                </button>
                <button
                  className="button button-secondary"
                  disabled={busy === `${name}:evaluate`}
                  onClick={() => run(name, "evaluate")}
                  type="button"
                >
                  {busy === `${name}:evaluate` ? "Evaluating…" : "Run evaluation"}
                </button>
                <button
                  className="button button-secondary"
                  disabled={busy === `${name}:status`}
                  onClick={() => run(name, "status")}
                  type="button"
                >
                  Status
                </button>
              </div>

              <JsonBlock value={reports[name]} />
            </article>
          );
        })}
      </div>

      <p className="notice">
        Dataset records are labelled SYNTHETIC_DATASET or EKACARE_EVALUATION and never appear as
        uploaded patient records. Metrics are only reported when real ground truth files are present.
      </p>
    </section>
  );
}
