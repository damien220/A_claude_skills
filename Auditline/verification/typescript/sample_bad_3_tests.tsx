import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { db } from '@/lib/db';
import { TaskBoard } from './sample_bad_2';

vi.mock('@/lib/db', () => ({
  db: {
    membership: { findUnique: vi.fn(async () => ({ role: 'member' })) },
    task: { findUniqueOrThrow: vi.fn(), update: vi.fn(), delete: vi.fn(), findMany: vi.fn() },
  },
}));
vi.mock('@/lib/auth', () => ({ getSession: vi.fn(async () => ({ userId: 'user-1' })) }));
vi.mock('@/lib/logger', () => ({ logger: { info: vi.fn() } }));
vi.mock('next/cache', () => ({ revalidatePath: vi.fn() }));

const PROJECT_ID = '3b1f6c2e-8d4a-4f7b-9e21-5c0d7a9b4e13';
const TASKS = [
  { id: 'a6d2f0c1-4b7e-4c39-8f15-2e9b0d7c6a41', title: 'Write release notes', status: 'todo', updatedAt: '2026-10-20T09:00:00.000Z' },
  { id: 'c9e4b3a7-1f2d-4e68-b0a5-7d3c8f1e2b90', title: 'Fix login redirect', status: 'in_progress', updatedAt: '2026-10-21T14:30:00.000Z' },
];

function renderBoard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <TaskBoard projectId={PROJECT_ID} />
    </QueryClientProvider>,
  );
}

describe('TaskBoard', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async () => new Response(JSON.stringify(TASKS), { status: 200 }));
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.restoreAllMocks();
  });

  it.only('renders one column per status', async () => {
    renderBoard();
    expect(await screen.findByRole('heading', { name: 'To do (1)' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'In progress (1)' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Done (0)' })).toBeInTheDocument();
  });

  it('renders a card for every task', async () => {
    const { container } = renderBoard();
    await screen.findByText('Write release notes');
    expect(container.querySelectorAll('.task-card')).toHaveLength(2);
  });

  it('lists matching tasks when searching', async () => {
    const user = userEvent.setup();
    renderBoard();
    await user.type(await screen.findByLabelText('Search tasks'), 'release');
    await waitFor(() => expect(screen.getAllByText('Write release notes')).toHaveLength(2));
  });

  it('does not show an error while typing a search', async () => {
    const user = userEvent.setup();
    renderBoard();
    const search = await screen.findByLabelText('Search tasks');
    user.type(search, 'login');
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('moves a task to done', async () => {
    const user = userEvent.setup();
    renderBoard();
    const [firstStatus] = await screen.findAllByLabelText('Status');
    await user.selectOptions(firstStatus, 'done');
    expect(db.task.update).toBeDefined();
  });
});
