import { useCallback, useEffect, useState } from 'react';
import { HydrationBoundary, QueryClient, dehydrate, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { revalidatePath } from 'next/cache';
import { z } from 'zod';
import { getSession } from '@/lib/auth';
import { db } from '@/lib/db';
import { logger } from '@/lib/logger';

const taskStatusSchema = z.enum(['todo', 'in_progress', 'done']);
type TaskStatus = z.infer<typeof taskStatusSchema>;
const taskSchema = z.object({ id: z.string().uuid(), title: z.string(), status: taskStatusSchema, updatedAt: z.string().datetime() });
type Task = z.infer<typeof taskSchema>;
type TaskRow = Omit<Task, 'updatedAt'> & { updatedAt: Date };
const COLUMNS: ReadonlyArray<{ status: TaskStatus; title: string }> = [
  { status: 'todo', title: 'To do' }, { status: 'in_progress', title: 'In progress' }, { status: 'done', title: 'Done' },
];
const toTask = (row: TaskRow): Task => ({ ...row, updatedAt: row.updatedAt.toISOString() });

// ---- Server: membership check, server actions and the page ----
async function requireProjectMember(projectId: string) {
  const session = await getSession();
  const membership = session && (await db.membership.findUnique({ where: { projectId_userId: { projectId, userId: session.userId } } }));
  if (!session || !membership) {
    throw new Error('Not a member of this project');
  }
  return session;
}

export async function updateTaskStatus(taskId: string, status: TaskStatus): Promise<Task> {
  'use server';
  const id = z.string().uuid().parse(taskId);
  const nextStatus = taskStatusSchema.parse(status);
  const { projectId } = await db.task.findUniqueOrThrow({ where: { id }, select: { projectId: true } });
  const session = await requireProjectMember(projectId);
  const row: TaskRow = await db.task.update({ where: { id }, data: { status: nextStatus } });
  logger.info({ taskId: id, userId: session.userId, status: nextStatus }, 'task status changed');
  revalidatePath(`/projects/${projectId}`);
  return toTask(row);
}

export async function deleteTask(taskId: string): Promise<void> {
  'use server';
  const id = z.string().uuid().parse(taskId);
  const { projectId } = await db.task.delete({ where: { id }, select: { projectId: true } });
  logger.info({ taskId: id, projectId }, 'task deleted');
  revalidatePath(`/projects/${projectId}`);
}

const serverQueryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 60_000 } } });

export async function ProjectBoardPage({ projectId }: { projectId: string }) {
  await requireProjectMember(projectId);
  await serverQueryClient.prefetchQuery({
    queryKey: ['tasks', projectId],
    queryFn: async () =>
      (await db.task.findMany({ where: { projectId }, orderBy: { position: 'asc' }, take: 500 })).map(toTask),
  });
  return (
    <HydrationBoundary state={dehydrate(serverQueryClient)}>
      <TaskBoard projectId={projectId} />
    </HydrationBoundary>
  );
}

// ---- Client: board UI ----
async function getTasks(projectId: string, term?: string, signal?: AbortSignal): Promise<Task[]> {
  const query = term ? `?${new URLSearchParams({ q: term })}` : '';
  const res = await fetch(`/api/projects/${encodeURIComponent(projectId)}/tasks${query}`, { signal });
  if (!res.ok) {
    throw new Error(`task list failed with ${res.status}`);
  }
  return z.array(taskSchema).parse(await res.json());
}
const relativeTime = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });
function formatAge(iso: string): string {
  const minutes = Math.round((Date.parse(iso) - Date.now()) / 60_000);
  return Math.abs(minutes) < 60 ? relativeTime.format(minutes, 'minute') : relativeTime.format(Math.round(minutes / 60), 'hour');
}

function UpdatedAgo({ updatedAt }: { updatedAt: string }) {
  const [label, setLabel] = useState(() => formatAge(updatedAt));
  useEffect(() => {
    const timer = window.setInterval(() => setLabel(formatAge(updatedAt)), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return <time dateTime={updatedAt}>Updated {label}</time>;
}

function TaskCard({ task, onMove, onDelete }: { task: Task; onMove: (s: TaskStatus) => void; onDelete: () => void }) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  return (
    <li className="task-card">
      <h3>{task.title}</h3>
      <UpdatedAgo updatedAt={task.updatedAt} />
      <label>
        Status
        <select value={task.status} onChange={(e) => onMove(taskStatusSchema.parse(e.target.value))}>
          {COLUMNS.map((c) => <option key={c.status} value={c.status}>{c.title}</option>)}
        </select>
      </label>
      {confirmingDelete
        ? <button type="button" onClick={onDelete}>Confirm delete</button>
        : <button type="button" onClick={() => setConfirmingDelete(true)}>Delete</button>}
    </li>
  );
}

function TaskSearch({ projectId }: { projectId: string }) {
  const [term, setTerm] = useState('');
  const [results, setResults] = useState<Task[]>([]);
  const [searchFailed, setSearchFailed] = useState(false);
  useEffect(() => {
    if (term.trim() === '') {
      setResults([]);
      setSearchFailed(false);
      return;
    }
    getTasks(projectId, term)
      .then((found) => { setSearchFailed(false); setResults(found); })
      .catch(() => setSearchFailed(true));
  }, [projectId, term]);
  return (
    <div role="search">
      <label htmlFor="task-search">Search tasks</label>
      <input id="task-search" type="search" value={term} onChange={(e) => setTerm(e.target.value)} />
      {searchFailed && <p role="alert">Search is unavailable right now.</p>}
      <ul aria-live="polite">{results.map((task) => <li key={task.id}>{task.title}</li>)}</ul>
    </div>
  );
}

export function TaskBoard({ projectId }: { projectId: string }) {
  const queryClient = useQueryClient();
  const tasksKey = ['tasks', projectId];
  const tasksQuery = useQuery({ queryKey: tasksKey, queryFn: ({ signal }) => getTasks(projectId, undefined, signal) });
  const moveTask = useMutation({
    mutationFn: ({ taskId, status }: { taskId: string; status: TaskStatus }) => updateTaskStatus(taskId, status),
    onMutate: async ({ taskId, status }) => {
      await queryClient.cancelQueries({ queryKey: tasksKey });
      queryClient.setQueryData<Task[]>(tasksKey, (prev) => prev?.map((t) => (t.id === taskId ? { ...t, status } : t)));
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tasksKey }),
  });
  const removeTask = useMutation({
    mutationFn: (taskId: string) => deleteTask(taskId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: tasksKey }),
  });
  if (tasksQuery.isPending) {
    return <div aria-busy="true">{COLUMNS.map((_, i) => <div key={i} className="board__column--placeholder" />)}</div>;
  }
  if (tasksQuery.isError) {
    return <p role="alert">The board could not be loaded.</p>;
  }
  return (
    <div className="board">
      <TaskSearch projectId={projectId} />
      {(moveTask.isError || removeTask.isError) && <p role="alert">Your last change was not saved.</p>}
      {COLUMNS.map((column) => {
        const columnTasks = tasksQuery.data.filter((task) => task.status === column.status);
        return (
          <section key={column.status} className="board__column" aria-label={column.title}>
            <h2>{column.title} ({columnTasks.length})</h2>
            {columnTasks.length && (
              <ul>
                {columnTasks.map((task, index) => (
                  <TaskCard
                    key={index}
                    task={task}
                    onMove={(status) => moveTask.mutate({ taskId: task.id, status })}
                    onDelete={() => removeTask.mutate(task.id)}
                  />
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
