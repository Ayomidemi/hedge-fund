"use client";

import { useEffect, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  createResearchNote,
  deleteResearchNote,
  getResearchNotes,
  type ResearchExperiment,
  type ResearchNote,
} from "@/lib/api";
import { LabPanel, formatDateTime } from "./research-lab-ui";

type NotebookPanelProps = {
  active: boolean;
  experiments: ResearchExperiment[];
};

export function NotebookPanel({ active, experiments }: NotebookPanelProps) {
  const [notes, setNotes] = useState<ResearchNote[] | null>(null);
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    if (!active || notes !== null) return;
    void loadNotes();
  }, [active, notes]);

  async function loadNotes() {
    try {
      setNotes(await getResearchNotes());
    } catch {
      setNotes([]);
      toast.error("Notebook entries could not be loaded.");
    }
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const formData = new FormData(form);
    const title = String(formData.get("title") ?? "").trim();
    const body = String(formData.get("body") ?? "").trim();
    const tags = String(formData.get("tags") ?? "")
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean)
      .slice(0, 10);
    const experimentId = String(formData.get("experiment_id") ?? "");

    if (!title || !body) {
      toast.error("Add a title and body for the notebook entry.");
      return;
    }

    setSaving(true);
    try {
      const note = await createResearchNote({
        title,
        body,
        tags,
        experiment_id: experimentId || null,
      });
      setNotes((current) => [note, ...(current ?? [])]);
      form.reset();
      toast.success("Notebook entry saved.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Entry could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(noteId: string) {
    setDeletingId(noteId);
    try {
      await deleteResearchNote(noteId);
      setNotes((current) => (current ?? []).filter((note) => note.id !== noteId));
      toast.success("Notebook entry deleted.");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Entry could not be deleted.");
    } finally {
      setDeletingId(null);
    }
  }

  const experimentNameById = new Map(
    experiments.map((experiment) => [experiment.id, experiment.name]),
  );

  return (
    <div className="grid gap-5 xl:grid-cols-[0.9fr_1fr]">
      <LabPanel
        title="New notebook entry"
        subtitle="Capture hypotheses, findings, and decisions; link entries to experiments"
      >
        <form className="space-y-4" onSubmit={handleCreate}>
          <Field label="Title">
            <input
              name="title"
              maxLength={255}
              className={inputClassName}
              placeholder="e.g. Momentum decay after regime shifts"
            />
          </Field>
          <Field label="Notes">
            <textarea
              name="body"
              rows={8}
              className={inputClassName}
              placeholder="What did you test, what did you observe, and what will you do next?"
            />
          </Field>
          <Field label="Tags (comma separated)">
            <input
              name="tags"
              className={inputClassName}
              placeholder="momentum, regime, costs"
            />
          </Field>
          <Field label="Linked experiment (optional)">
            <select name="experiment_id" defaultValue="" className={inputClassName}>
              <option value="">No linked experiment</option>
              {experiments.map((experiment) => (
                <option key={experiment.id} value={experiment.id}>
                  {experiment.name}
                </option>
              ))}
            </select>
          </Field>
          <button type="submit" disabled={saving} className={buttonPrimaryClassName}>
            {saving ? "Saving…" : "Save entry"}
          </button>
        </form>
      </LabPanel>

      <LabPanel title="Lab notebook" subtitle="Your research log, newest first">
        {notes === null ? (
          <p className="text-sm text-zinc-500">Loading notebook…</p>
        ) : notes.length === 0 ? (
          <p className="text-sm text-zinc-500">
            No entries yet. Write down what you test so future-you can trust past-you.
          </p>
        ) : (
          <div className="space-y-4">
            {notes.map((note) => (
              <article
                key={note.id}
                className="rounded-lg border border-zinc-100 bg-zinc-50 p-4 dark:border-zinc-900 dark:bg-zinc-900/50"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <h4 className="font-medium">{note.title}</h4>
                    <p className="mt-0.5 text-xs text-zinc-500">
                      {formatDateTime(note.created_at)}
                      {note.experiment_id && (
                        <>
                          {" · "}
                          <span className="text-zinc-600 dark:text-zinc-400">
                            {experimentNameById.get(note.experiment_id) ?? "Linked experiment"}
                          </span>
                        </>
                      )}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => void handleDelete(note.id)}
                    disabled={deletingId !== null}
                    className={buttonSecondaryClassName}
                  >
                    {deletingId === note.id ? "Deleting…" : "Delete"}
                  </button>
                </div>
                <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-zinc-700 dark:text-zinc-300">
                  {note.body}
                </p>
                {note.tags.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {note.tags.map((tag) => (
                      <span
                        key={tag}
                        className="rounded-md bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400"
                      >
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </LabPanel>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</span>
      {children}
    </label>
  );
}
