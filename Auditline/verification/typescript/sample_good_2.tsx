import { useEffect, useId, useState, type ReactNode } from 'react';
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { z } from 'zod';

const invoiceStatusSchema = z.enum(['draft', 'open', 'paid', 'void']);
type StatusFilter = z.infer<typeof invoiceStatusSchema> | 'all';
const count = z.number().int().nonnegative();

// Amounts arrive as integers in the currency's ISO 4217 minor unit; dueDate is a calendar date.
const invoiceSchema = z.object({
  id: z.string(), number: z.string(), customerName: z.string(), amountMinor: count, currency: z.string().regex(/^[A-Z]{3}$/),
  status: invoiceStatusSchema, dueDate: z.string().regex(/^\d{4}-\d{2}-\d{2}$/), starred: z.boolean(),
});
const invoicePageSchema = z.object({ items: z.array(invoiceSchema), pageCount: count, paidCount: count, totalCount: count });
type InvoicePage = z.infer<typeof invoicePageSchema>;
type InvoiceFilters = { status: StatusFilter; search: string; page: number };
const PAGE_SIZE = 25;
const TABLE_HEADERS = ['Number', 'Customer', 'Amount', 'Due', 'Status', 'Starred'];
const STATUS_FILTERS: ReadonlyArray<{ value: StatusFilter; label: string }> = [
  { value: 'all', label: 'All' }, { value: 'open', label: 'Open' }, { value: 'paid', label: 'Paid' },
  { value: 'draft', label: 'Draft' }, { value: 'void', label: 'Void' },
];
const dueDateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeZone: 'UTC' });

async function fetchInvoicePage(filters: InvoiceFilters, signal: AbortSignal): Promise<InvoicePage> {
  const status = filters.status === 'all' ? '' : filters.status;
  const query = { page: String(filters.page), pageSize: String(PAGE_SIZE), status, q: filters.search };
  const params = new URLSearchParams(Object.entries(query).filter(([, value]) => value !== ''));
  const res = await fetch(`/api/invoices?${params}`, { signal });
  if (!res.ok) {
    throw new Error(`invoice list failed with ${res.status}`);
  }
  return invoicePageSchema.parse(await res.json());
}

async function setInvoiceStarred(id: string, starred: boolean): Promise<void> {
  const res = await fetch(`/api/invoices/${encodeURIComponent(id)}/star`, { method: starred ? 'PUT' : 'DELETE' });
  if (!res.ok) {
    throw new Error(`star update failed with ${res.status}`);
  }
}

function formatMoney(amountMinor: number, currency: string): string {
  const format = new Intl.NumberFormat(undefined, { style: 'currency', currency });
  const digits = format.resolvedOptions().maximumFractionDigits ?? 2;
  return format.format(amountMinor / 10 ** digits);
}

function localIsoDate(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

function RefreshedAgo({ updatedAt }: { updatedAt: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, []);
  const minutes = Math.max(0, Math.floor((now - updatedAt) / 60_000));
  return <span className="invoices__refreshed">{minutes === 0 ? 'Updated just now' : `Updated ${minutes} min ago`}</span>;
}

export function InvoiceTable() {
  const queryClient = useQueryClient();
  const statusId = useId();
  const searchId = useId();
  const [status, setStatus] = useState<StatusFilter>('all');
  const [searchInput, setSearchInput] = useState('');
  const [page, setPage] = useState(1);
  const search = useDebouncedValue(searchInput.trim(), 300);
  const filters: InvoiceFilters = { status, search, page };
  const invoicesQuery = useQuery({
    queryKey: ['invoices', filters],
    queryFn: ({ signal }) => fetchInvoicePage(filters, signal),
    placeholderData: keepPreviousData,
  });

  const star = useMutation({
    mutationFn: ({ id, starred }: { id: string; starred: boolean }) => setInvoiceStarred(id, starred),
    onMutate: async ({ id, starred }) => {
      const key = ['invoices', filters];
      await queryClient.cancelQueries({ queryKey: key });
      const previous = queryClient.getQueryData<InvoicePage>(key);
      queryClient.setQueryData<InvoicePage>(key, (old) =>
        old && { ...old, items: old.items.map((inv) => (inv.id === id ? { ...inv, starred } : inv)) },
      );
      return { key, previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) {
        queryClient.setQueryData(context.key, context.previous);
      }
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['invoices'] }),
  });
  function changeStatus(value: string) {
    const next = STATUS_FILTERS.find((option) => option.value === value);
    if (next) {
      setStatus(next.value);
      setPage(1);
    }
  }

  let results: ReactNode;
  if (invoicesQuery.isPending) {
    results = <ul aria-busy="true">{Array.from({ length: 5 }, (_, row) => <li key={row} className="invoices__skeleton-row" />)}</ul>;
  } else if (invoicesQuery.isError) {
    results = <p role="alert">Invoices could not be loaded. <button type="button" onClick={() => invoicesQuery.refetch()}>Try again</button></p>;
  } else {
    const data = invoicesQuery.data;
    const today = localIsoDate(new Date());
    const paidRatio = data.totalCount === 0 ? 0 : data.paidCount / data.totalCount;
    results = (
      <>
        <p>
          <progress value={paidRatio} max={1} aria-label="Share of invoices paid" /> {Math.round(paidRatio * 100)}% paid
          {' · '}<RefreshedAgo updatedAt={invoicesQuery.dataUpdatedAt} />
        </p>
        {data.items.length > 0 ? (
          <table>
            <thead>
              <tr>{TABLE_HEADERS.map((header) => <th key={header} scope="col">{header}</th>)}</tr>
            </thead>
            <tbody>
              {data.items.map((invoice) => (
                <tr key={invoice.id}>
                  <td>{invoice.number}</td>
                  <td>{invoice.customerName}</td>
                  <td>{formatMoney(invoice.amountMinor, invoice.currency)}</td>
                  <td>
                    {dueDateFormat.format(new Date(`${invoice.dueDate}T00:00:00Z`))}
                    {invoice.status === 'open' && invoice.dueDate < today && ' (overdue)'}
                  </td>
                  <td>{invoice.status}</td>
                  <td>
                    <button type="button" aria-pressed={invoice.starred} aria-label={`Star invoice ${invoice.number}`}
                      onClick={() => star.mutate({ id: invoice.id, starred: !invoice.starred })}>
                      {invoice.starred ? '★' : '☆'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p>No invoices match these filters.</p>
        )}
        <nav aria-label="Invoice pages">
          <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1}>Previous</button>
          <span>Page {page} of {Math.max(data.pageCount, 1)}</span>
          <button type="button" onClick={() => setPage((p) => p + 1)} disabled={invoicesQuery.isPlaceholderData || page >= data.pageCount}>Next</button>
        </nav>
      </>
    );
  }
  return (
    <section aria-labelledby="invoices-heading">
      <h2 id="invoices-heading">Invoices</h2>
      <label htmlFor={statusId}>Status</label>
      <select id={statusId} value={status} onChange={(e) => changeStatus(e.target.value)}>
        {STATUS_FILTERS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
      </select>
      <label htmlFor={searchId}>Search</label>
      <input id={searchId} type="search" value={searchInput} onChange={(e) => { setSearchInput(e.target.value); setPage(1); }} />
      {star.isError && <p role="alert">The star could not be saved. Please try again.</p>}
      {results}
    </section>
  );
}
