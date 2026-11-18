import { useEffect, useState } from "react";
import { Alert, Button, Card, Spinner } from "../components/ui";
import { fetchExaSettings, saveExaKeys } from "../lib/api";
import type { ExaSettings } from "../lib/api";

export function SettingsPage() {
  const [settings, setSettings] = useState<ExaSettings | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      setSettings(await fetchExaSettings());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const keys = draft
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter((line) => line !== "");
    if (keys.length === 0) {
      setError("Enter at least one Exa API key.");
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const result = await saveExaKeys(keys);
      setDraft("");
      setNotice(`${result.count} key(s) saved. Rotation starts from the first key.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-5">
      <header>
        <h1 className="m-0 text-lg font-semibold text-slate-100">Settings</h1>
        <p className="mt-1 mb-0 text-[13px] text-slate-400">
          Configure the Exa API keys used for web search. Keys are entered one per
          line and rotated automatically when Exa rate-limits or rejects one.
        </p>
      </header>

      {error && <Alert>{error}</Alert>}
      {notice && <Alert tone="ok">{notice}</Alert>}

      <Card className="flex flex-col gap-3 p-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="m-0 text-[13px] font-semibold text-slate-200">Exa key pool</h2>
          {loading && <Spinner />}
        </div>

        {settings && settings.keys.length > 0 ? (
          <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
            {settings.keys.map((key, index) => (
              <li
                key={`${key.masked}-${index}`}
                className="flex items-center justify-between rounded-md border border-slate-800 bg-slate-950/40 px-3 py-2 text-[13px]"
              >
                <span className="font-mono text-slate-300">{key.masked}</span>
                <span className="text-[11px] uppercase tracking-wide text-slate-500">
                  {key.source}
                </span>
              </li>
            ))}
          </ul>
        ) : (
          !loading && (
            <p className="m-0 text-[13px] text-slate-400">No Exa keys configured yet.</p>
          )
        )}

        {settings?.env_override && (
          <Alert tone="info">
            <code>EXA_API_KEYS</code> is set in the environment and takes precedence
            over keys saved here.
          </Alert>
        )}

        <form className="flex flex-col gap-2" onSubmit={submit}>
          <label className="text-[12px] font-medium text-slate-300" htmlFor="exa-keys">
            Add or replace keys
          </label>
          <textarea
            id="exa-keys"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={4}
            spellCheck={false}
            placeholder={"exa-key-one\nexa-key-two"}
            className="w-full resize-y rounded-md border border-slate-700 bg-slate-950/60 px-3 py-2 font-mono text-[13px] text-slate-100 outline-none placeholder:text-slate-600 focus:border-sky-500"
          />
          <div className="flex items-center gap-2">
            <Button type="submit" disabled={saving}>
              {saving ? "Saving..." : "Save keys"}
            </Button>
            <span className="text-[12px] text-slate-500">
              Saving replaces the stored list; duplicate keys are dropped.
            </span>
          </div>
        </form>
      </Card>

      <Card className="flex flex-col gap-2 p-4">
        <h2 className="m-0 text-[13px] font-semibold text-slate-200">How rotation works</h2>
        <ul className="m-0 list-disc pl-5 text-[13px] text-slate-400">
          <li>Each search uses the next key in round-robin order.</li>
          <li>HTTP 401 or 429 moves immediately to the following key.</li>
          <li>
            Environment variables <code>EXA_API_KEYS</code> or <code>EXA_API_KEY</code>
            override keys saved in the UI.
          </li>
        </ul>
      </Card>
    </section>
  );
}
