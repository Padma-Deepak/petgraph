import { useEffect, useState } from 'react';
import { dismissReminder, fetchReminders, snoozeReminder } from '../api/client';
import type { Reminder } from '../types';

const KIND_ICON: Record<Reminder['kind'], string> = {
  vaccine_due: '💉',
  follow_up: '📅',
  medication_end: '💊',
};

const KIND_LABEL: Record<Reminder['kind'], string> = {
  vaccine_due: 'Vaccination',
  follow_up: 'Follow-up visit',
  medication_end: 'Medication check',
};

interface Props {
  onChanged?: () => void;
}

export default function RemindersPanel({ onChanged }: Props) {
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const data = await fetchReminders();
      setReminders(
        [...data.reminders].sort((a, b) => (a.due_date ?? '9999').localeCompare(b.due_date ?? '9999')),
      );
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDismiss(id: string) {
    setBusy(id);
    try {
      await dismissReminder(id);
      await load();
      onChanged?.();
    } finally {
      setBusy(null);
    }
  }

  async function handleSnooze(id: string) {
    setBusy(id);
    try {
      const until = new Date(Date.now() + 7 * 24 * 3600 * 1000).toISOString().slice(0, 10);
      await snoozeReminder(id, until);
      await load();
      onChanged?.();
    } finally {
      setBusy(null);
    }
  }

  const today = new Date().toISOString().slice(0, 10);

  return (
    <div className="max-w-2xl mx-auto w-full p-6 flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Reminders</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Upcoming care dates found in your pets' records — boosters, rechecks, and medication reviews.
        </p>
      </div>

      {loaded && reminders.length === 0 && (
        <div className="text-center py-12 text-gray-600">
          <span className="text-3xl block mb-2">✅</span>
          <p className="text-sm">Nothing coming up. New reminders appear automatically when records are added.</p>
        </div>
      )}

      {reminders.map((r) => {
        const overdue = (r.due_date ?? '9999') < today;
        const soon =
          !overdue &&
          r.due_date != null &&
          (new Date(r.due_date).getTime() - new Date(today).getTime()) / 86400000 <= 30;
        return (
          <div
            key={r.id}
            className={`border rounded-xl p-4 flex gap-3 items-start animate-fade-in ${
              overdue ? 'border-red-800/70 bg-red-950/20' : 'border-[#30363d] bg-[#161b22]'
            }`}
          >
            <span className="text-xl leading-none mt-0.5">{KIND_ICON[r.kind] ?? '🔔'}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-white">{r.title}</span>
                {overdue && (
                  <span className="text-[9px] uppercase tracking-wide bg-red-900/70 text-red-300 px-1.5 py-0.5 rounded">
                    Overdue
                  </span>
                )}
                {soon && (
                  <span className="text-[9px] uppercase tracking-wide bg-amber-900/60 text-amber-300 px-1.5 py-0.5 rounded">
                    Due soon
                  </span>
                )}
              </div>
              <p className="text-[11px] text-gray-500 mt-1">
                {KIND_LABEL[r.kind] ?? 'Reminder'}
                {r.due_date ? ` · due ${r.due_date}` : ''}
                {r.pet_name ? ` · ${r.pet_name}` : ''}
              </p>
              {r.details && <p className="text-xs text-gray-400 mt-1.5 leading-relaxed">{r.details}</p>}
            </div>
            <div className="flex flex-col gap-1.5 shrink-0">
              <button
                onClick={() => handleSnooze(r.id)}
                disabled={busy === r.id}
                className="text-[10px] text-gray-400 hover:text-white border border-[#30363d] hover:border-gray-500 rounded px-2 py-1 transition-colors disabled:opacity-40"
              >
                Snooze 1 week
              </button>
              <button
                onClick={() => handleDismiss(r.id)}
                disabled={busy === r.id}
                className="text-[10px] text-gray-500 hover:text-red-300 transition-colors disabled:opacity-40"
              >
                Dismiss
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
