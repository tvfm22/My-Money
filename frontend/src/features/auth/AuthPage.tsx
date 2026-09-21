import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useLocation, useNavigate } from 'react-router-dom'
import { Wallet } from 'lucide-react'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { useAuth } from '../../hooks/useAuth'
import { errorMessage, fieldErrors } from '../../services/client'
import { MIN_PASSWORD, toLatinDigits } from '../../utils/format'

// ---------------------------------------------------------------------------
// Validation
//
// Messages are written for a person, not a developer. The email regex is
// deliberately permissive — rejecting a valid address is worse than accepting
// an unusual one, and the server is the real authority.
// ---------------------------------------------------------------------------

const loginSchema = z.object({
  email: z.string().min(1, 'ایمیل را وارد کنید.').email('ایمیل واردشده معتبر نیست.'),
  password: z.string().min(1, 'رمز عبور را وارد کنید.'),
})

const registerSchema = z
  .object({
    first_name: z.string().max(150, 'نام بیش از حد طولانی است.').optional(),
    last_name: z.string().max(150, 'نام خانوادگی بیش از حد طولانی است.').optional(),
    email: z.string().min(1, 'ایمیل را وارد کنید.').email('ایمیل واردشده معتبر نیست.'),
    password: z
      .string()
      .min(8, `رمز عبور باید حداقل ${MIN_PASSWORD} کاراکتر باشد.`)
      .max(128, 'رمز عبور بیش از حد طولانی است.'),
    password_confirm: z.string().min(1, 'تکرار رمز عبور را وارد کنید.'),
  })
  .refine((data) => data.password === data.password_confirm, {
    message: 'رمز عبور و تکرار آن یکسان نیستند.',
    path: ['password_confirm'],
  })

type LoginValues = z.infer<typeof loginSchema>
type RegisterValues = z.infer<typeof registerSchema>

export function AuthPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const navigate = useNavigate()
  const location = useLocation()
  const { login, register: registerUser } = useAuth()

  const redirectTo = (location.state as { from?: string } | null)?.from ?? '/'

  return (
    <div className="flex min-h-dvh flex-col bg-canvas">
      <div className="flex flex-1 items-center justify-center px-4 py-10">
        <div className="w-full max-w-md">
          {/* Brand */}
          <div className="mb-8 flex flex-col items-center gap-3 text-center">
            <span className="flex size-14 items-center justify-center rounded-card bg-brand-600 text-white shadow-raised">
              <Wallet className="size-7" aria-hidden="true" />
            </span>
            <div>
              <h1 className="text-xl font-bold text-ink">مالی من</h1>
              <p className="mt-1 text-[13px] leading-6 text-ink-soft">
                درآمد، هزینه، بودجه و دارایی‌هایتان را یک‌جا و به زبان فارسی مدیریت کنید.
              </p>
            </div>
          </div>

          <div className="rounded-card border border-border bg-surface p-5 shadow-card sm:p-6">
            {/* Mode switch */}
            <div className="mb-5 grid grid-cols-2 gap-1 rounded-control bg-surface-muted p-1">
              {(['login', 'register'] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setMode(option)}
                  aria-pressed={mode === option}
                  className={[
                    'h-10 rounded-control text-[13px] font-medium transition-colors',
                    mode === option ? 'bg-surface text-ink shadow-card' : 'text-ink-soft hover:text-ink',
                  ].join(' ')}
                >
                  {option === 'login' ? 'ورود' : 'ثبت‌نام'}
                </button>
              ))}
            </div>

            {mode === 'login' ? (
              <LoginForm
                onSuccess={() => navigate(redirectTo, { replace: true })}
                onSubmit={login}
              />
            ) : (
              <RegisterForm
                onSuccess={() => navigate(redirectTo, { replace: true })}
                onSubmit={registerUser}
              />
            )}
          </div>

          {mode === 'register' ? (
            <p className="mt-5 text-center text-xs leading-5 text-ink-faint">
              با ثبت‌نام، دسته‌بندی‌های پیش‌فرض فارسی برای شما ساخته می‌شود.
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------

function LoginForm({
  onSubmit,
  onSuccess,
}: {
  onSubmit: (email: string, password: string) => Promise<void>
  onSuccess: () => void
}) {
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: '', password: '' },
  })

  const submit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await onSubmit(values.email.trim().toLowerCase(), values.password)
      onSuccess()
    } catch (error) {
      // Field-level errors from the API are attached to their inputs; anything
      // unrecognised becomes a calm sentence above the button.
      const fields = fieldErrors(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field === 'email' || field === 'password') {
          setError(field, { message })
          matched = true
        }
      }
      setFormError(matched ? null : errorMessage(error, 'ورود انجام نشد. اطلاعات را بررسی کنید.'))
    }
  })

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <Input
        label="ایمیل"
        type="email"
        inputMode="email"
        dir="ltr"
        autoComplete="email"
        placeholder="name@example.com"
        error={errors.email?.message}
        {...register('email', { onChange: () => setFormError(null) })}
      />

      <Input
        label="رمز عبور"
        type="password"
        dir="ltr"
        autoComplete="current-password"
        placeholder="••••••••"
        error={errors.password?.message}
        {...register('password', { onChange: () => setFormError(null) })}
      />

      {formError ? (
        <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
          {formError}
        </p>
      ) : null}

      <Button type="submit" fullWidth size="lg" isLoading={isSubmitting}>
        ورود به حساب
      </Button>
    </form>
  )
}

// ---------------------------------------------------------------------------

function RegisterForm({
  onSubmit,
  onSuccess,
}: {
  onSubmit: (payload: {
    email: string
    password: string
    password_confirm: string
    first_name?: string
    last_name?: string
  }) => Promise<void>
  onSuccess: () => void
}) {
  const [formError, setFormError] = useState<string | null>(null)

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<RegisterValues>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      first_name: '',
      last_name: '',
      email: '',
      password: '',
      password_confirm: '',
    },
  })

  const submit = handleSubmit(async (values) => {
    setFormError(null)
    try {
      await onSubmit({
        email: values.email.trim().toLowerCase(),
        // Normalise Persian/Arabic digits the user may have typed on a
        // Persian keyboard layout.
        password: toLatinDigits(values.password),
        password_confirm: toLatinDigits(values.password_confirm),
        first_name: values.first_name?.trim() || undefined,
        last_name: values.last_name?.trim() || undefined,
      })
      onSuccess()
    } catch (error) {
      const fields = fieldErrors(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (
          field === 'email' ||
          field === 'password' ||
          field === 'password_confirm' ||
          field === 'first_name' ||
          field === 'last_name'
        ) {
          setError(field, { message })
          matched = true
        }
      }
      setFormError(matched ? null : errorMessage(error, 'ثبت‌نام انجام نشد. دوباره تلاش کنید.'))
    }
  })

  return (
    <form onSubmit={submit} noValidate className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Input
          label="نام"
          autoComplete="given-name"
          placeholder="مثلاً سارا"
          error={errors.first_name?.message}
          {...register('first_name')}
        />
        <Input
          label="نام خانوادگی"
          autoComplete="family-name"
          placeholder="مثلاً محمدی"
          error={errors.last_name?.message}
          {...register('last_name')}
        />
      </div>

      <Input
        label="ایمیل"
        type="email"
        inputMode="email"
        dir="ltr"
        autoComplete="email"
        placeholder="name@example.com"
        error={errors.email?.message}
        {...register('email', { onChange: () => setFormError(null) })}
      />

      <Input
        label="رمز عبور"
        type="password"
        dir="ltr"
        autoComplete="new-password"
        placeholder={`حداقل ${MIN_PASSWORD} کاراکتر`}
        hint="برای امنیت بیشتر از ترکیب حرف، عدد و نماد استفاده کنید."
        error={errors.password?.message}
        {...register('password')}
      />

      <Input
        label="تکرار رمز عبور"
        type="password"
        dir="ltr"
        autoComplete="new-password"
        placeholder="••••••••"
        error={errors.password_confirm?.message}
        {...register('password_confirm')}
      />

      {formError ? (
        <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
          {formError}
        </p>
      ) : null}

      <Button type="submit" fullWidth size="lg" isLoading={isSubmitting}>
        ساخت حساب
      </Button>
    </form>
  )
}
