# Forms & Validation — TypeScript Frontend Reference

Grounded in the **React Hook Form docs**, the **Zod docs**, and **WCAG 2.1 SC 3.3.1/3.3.2**
(error identification and labels). Standard: **React Hook Form (RHF) + `zodResolver`** for any
form beyond a single input.

---

## Why not `useState` per field

Controlled-everything forms re-render the whole form on every keystroke, scatter validation
across handlers, and duplicate the validity rules in TS types. RHF is uncontrolled internally
(refs, not state) — keystrokes don't re-render — and one Zod schema is both the validation and
the type.

```tsx
// WRONG — 3 states, hand-rolled validation, whole form re-renders per keystroke
const [email, setEmail] = useState('');
const [password, setPassword] = useState('');
const [errors, setErrors] = useState<Record<string, string>>({});
const handleSubmit = () => {
  if (!email.includes('@')) { setErrors({ email: 'Invalid' }); return; }
  ...
};
```

```tsx
// CORRECT — schema once; type derived; validation, errors, and submit-guard for free
const SignUpSchema = z.object({
  email: z.string().email('Enter a valid email address'),
  password: z.string().min(12, 'At least 12 characters'),
});
type SignUpInput = z.infer<typeof SignUpSchema>;

export function SignUpForm({ onSignUp }: Props) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<SignUpInput>({ resolver: zodResolver(SignUpSchema) });

  return (
    <form onSubmit={handleSubmit(onSignUp)} noValidate>
      <label htmlFor="email">Email</label>
      <input id="email" type="email" aria-describedby="email-error" {...register('email')} />
      <p id="email-error" role="alert">{errors.email?.message}</p>

      <label htmlFor="password">Password</label>
      <input id="password" type="password" {...register('password')} />
      <p role="alert">{errors.password?.message}</p>

      <button type="submit" disabled={isSubmitting}>Create account</button>
    </form>
  );
}
```

`handleSubmit` blocks submission until the schema passes — never write a manual
`if (hasErrors) return` guard.

---

## `register` vs `Controller`

| Input | API |
|---|---|
| Native HTML (`input`, `select`, `textarea`) | `register('field')` — ref-based, zero re-renders |
| Custom / third-party (date picker, combobox, Radix/MUI) | `<Controller>` — bridges value/onChange components |

```tsx
// CORRECT — Controller only where the component demands controlled props
<Controller
  name="birthDate"
  control={control}
  render={({ field, fieldState }) => (
    <DatePicker
      value={field.value}
      onChange={field.onChange}
      onBlur={field.onBlur}
      errorMessage={fieldState.error?.message}
    />
  )}
/>
```

Never wrap a native input in `Controller` — you pay re-renders for nothing.

---

## Accessible error display (WCAG 3.3.1)

Errors must be programmatically associated with their field and announced to screen readers.

```tsx
// WRONG — visually adjacent but invisible to assistive tech; placeholder as label
<input placeholder="Email" {...register('email')} />
{errors.email && <span className="red">{errors.email.message}</span>}
```

```tsx
// CORRECT — label, aria-invalid, aria-describedby, role="alert"
<label htmlFor="email">Email</label>
<input
  id="email"
  type="email"
  aria-invalid={!!errors.email}
  aria-describedby={errors.email ? 'email-error' : undefined}
  {...register('email')}
/>
{errors.email && (
  <p id="email-error" role="alert">
    {errors.email.message}
  </p>
)}
```

Set `noValidate` on the `<form>` — RHF + Zod own validation; the browser's native bubbles
conflict with it.

---

## Server-side failures → `setError`

Validation the server rejects (duplicate email, expired coupon) maps back onto the form,
field-targeted when possible.

```tsx
// CORRECT
const onSubmit = async (input: SignUpInput) => {
  try {
    await signUp(input);
  } catch (err) {
    if (err instanceof ApiError && err.code === 'EMAIL_TAKEN') {
      setError('email', { message: 'This email is already registered' });
    } else {
      setError('root.server', { message: humanize(err) });   // form-level error
    }
  }
};

{errors.root?.server && <p role="alert">{errors.root.server.message}</p>}
```

---

## `watch` sparingly; `useWatch` for subscriptions

`watch()` with no args subscribes the whole component to every field — back to
re-render-per-keystroke. Subscribe to the one field you need, in the smallest component.

```tsx
// WRONG — whole form re-renders on any keystroke anywhere
const values = watch();

// CORRECT — isolated subscription in a child component
function PasswordStrength({ control }: { control: Control<SignUpInput> }) {
  const password = useWatch({ control, name: 'password' });
  return <StrengthMeter value={score(password)} />;
}
```

---

## Field arrays

Dynamic lists (line items, phone numbers) use `useFieldArray` — stable `field.id` keys, typed
append/remove. Never `useState<Item[]>` + index juggling next to RHF.

```tsx
// CORRECT
const { fields, append, remove } = useFieldArray({ control, name: 'lineItems' });

{fields.map((field, index) => (
  <div key={field.id}>                          {/* field.id, never index */}
    <input {...register(`lineItems.${index}.description`)} />
    <button type="button" onClick={() => remove(index)}>Remove</button>
  </div>
))}
<button type="button" onClick={() => append({ description: '', qty: 1 })}>Add line</button>
```

---

## Reset and default values

`reset()` after a successful submit; pass fetched entities as `defaultValues` via the `values`
prop (RHF v7.43+) or a keyed remount — never `setValue` field-by-field.

```tsx
// CORRECT — edit form bound to fetched data
const { data: user } = useQuery({ queryKey: userKeys.detail(id), queryFn: ... });
const form = useForm<ProfileInput>({
  resolver: zodResolver(ProfileSchema),
  values: user,                       // re-syncs when the query updates
});

const onSubmit = async (input: ProfileInput) => {
  await updateProfile.mutateAsync(input);
  form.reset(input);                  // clears dirty state; isDirty drives "unsaved changes" UI
};
```
