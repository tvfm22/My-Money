import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { MIN_PASSWORD } from '../../utils/format'
import { z } from 'zod'
import { LogOut, Moon, Plus, Sun, User as UserIcon } from 'lucide-react'
import { Card, CardHeader } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Badge } from '../../components/ui/Badge'
import { AccountForm } from './AccountForm'
import { CategoryManager } from './CategoryManager'
import { useAuth } from '../../hooks/useAuth'
import { useTheme } from '../../hooks/useTheme'
import { useAccounts, useUpdateProfile } from '../../hooks/queries'
import { authApi } from '../../services/api'
import { errorMessage, fieldErrors } from '../../services/client'
import type { Account } from '../../types'

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

const profileSchema = z.object({
  first_name: z.string().max(150, 'نام بیش از حد طولانی است.').optional(),
  last_name: z.string().max(150, 'نام خانوادگی بیش از حد طولانی است.').optional(),
})

const passwordSchema = z
  .object({
    current_password: z.string().min(1, 'رمز عبور فعلی را وارد کنید.'),
    new_password: z
      .string()
      .min(8, `رمز عبور جدید باید حداقل ${MIN_PASSWORD} کاراکتر باشد.`)
      .max(128, 'رمز عبور بیش از حد طولانی است.'),
    new_password_confirm: z.string().min(1, 'تکرار رمز عبور جدید را وارد کنید.'),
  })
  .refine((data) => data.new_password === data.new_password_confirm, {
    message: 'رمز عبور جدید و تکرار آن یکسان نیستند.',
    path: ['new_password_confirm'],
  })

type ProfileValues = z.infer<typeof profileSchema>
type PasswordValues = z.infer<typeof passwordSchema>

/** Tabs keep the settings screen from becoming one long scroll. */
type Tab = 'profile' | 'accounts' | 'categories' | 'security'

const TABS: Array<{ key: Tab; label: string }> = [
  { key: 'profile', label: 'حساب کاربری' },
  { key: 'accounts', label: 'حساب‌های مالی' },
  { key: 'categories', label: 'دسته‌بندی‌ها' },
  { key: 'security', label: 'امنیت' },
]

export function SettingsPage() {
  const [tab, setTab] = useState<Tab>('profile')

  return (
    <>
      <div className="mb-4">
        <h1 className="text-lg font-bold text-ink lg:text-xl">تنظیمات</h1>
        <p className="mt-1 text-[12.5px] text-ink-soft">
          حساب کاربری، حساب‌های مالی و دسته‌بندی‌ها
        </p>
      </div>

      <div className="mb-4 flex gap-1 overflow-x-auto rounded-control bg-surface-muted p-1 no-scrollbar">
        {TABS.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            aria-pressed={tab === item.key}
            className={[
              'h-10 shrink-0 rounded-control px-4 text-[13px] font-medium transition-colors',
              tab === item.key
                ? 'bg-surface text-ink shadow-card'
                : 'text-ink-soft hover:text-ink',
            ].join(' ')}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'profile' ? <ProfileSection /> : null}
      {tab === 'accounts' ? <AccountsSection /> : null}
      {tab === 'categories' ? <CategoryManager /> : null}
      {tab === 'security' ? <SecuritySection /> : null}
    </>
  )
}

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------

function ProfileSection() {
  const { user, logout } = useAuth()
  const updateProfile = useUpdateProfile()
  const [feedback, setFeedback] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      first_name: user?.first_name ?? '',
      last_name: user?.last_name ?? '',
    },
  })

  // `defaultValues` is read once, on the first render — and on that render
  // `user` is still `null` because the profile arrives asynchronously from
  // `/auth/me/`. Without this the fields would stay permanently blank for a
  // signed-in user, and saving would overwrite their real name with "".
  // `reset` is the supported way to push server state into an existing form.
  useEffect(() => {
    if (!user) return
    reset({ first_name: user.first_name ?? '', last_name: user.last_name ?? '' })
  }, [user, reset])

  const submit = handleSubmit(async (values) => {
    setFeedback(null)
    try {
      await updateProfile.mutateAsync({
        first_name: values.first_name?.trim() ?? '',
        last_name: values.last_name?.trim() ?? '',
      })
      setFeedback({ tone: 'ok', text: 'اطلاعات با موفقیت ذخیره شد.' })
    } catch (error) {
      setFeedback({
        tone: 'error',
        text: errorMessage(error, 'ذخیره اطلاعات انجام نشد. دوباره تلاش کنید.'),
      })
    }
  })

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader title="اطلاعات حساب" subtitle="نام نمایشی شما در برنامه" />

        <div className="mt-4 flex items-center gap-3 rounded-card bg-surface-muted p-3">
          <span className="flex size-12 items-center justify-center rounded-pill bg-brand-600 text-[18px] font-semibold text-white">
            {(user?.display_name || user?.email || '؟').trim().charAt(0)}
          </span>
          <div className="min-w-0">
            <p className="truncate text-[14px] font-semibold text-ink">
              {user?.display_name || 'کاربر'}
            </p>
            <p className="truncate text-[11.5px] text-ink-faint" dir="ltr">
              {user?.email}
            </p>
          </div>
        </div>

        <form onSubmit={submit} noValidate className="mt-4 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="نام"
              placeholder="مثلاً سارا"
              error={errors.first_name?.message}
              {...register('first_name')}
            />
            <Input
              label="نام خانوادگی"
              placeholder="مثلاً محمدی"
              error={errors.last_name?.message}
              {...register('last_name')}
            />
          </div>

          {feedback ? (
            <p
              role="status"
              className={[
                'rounded-control px-3 py-2 text-xs',
                feedback.tone === 'ok'
                  ? 'bg-positive-50 text-positive-700'
                  : 'bg-critical-50 text-critical-700',
              ].join(' ')}
            >
              {feedback.text}
            </p>
          ) : null}

          <Button type="submit" isLoading={isSubmitting}>
            ذخیره تغییرات
          </Button>
        </form>
      </Card>

      <ThemeCard />

      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[14px] font-semibold text-ink">خروج از حساب</p>
            <p className="mt-0.5 text-[11.5px] leading-5 text-ink-faint">
              برای ورود دوباره باید ایمیل و رمز عبور خود را وارد کنید.
            </p>
          </div>
          <Button
            variant="secondary"
            onClick={() => void logout()}
            leadingIcon={<LogOut className="size-4" aria-hidden="true" />}
            className="shrink-0"
          >
            خروج
          </Button>
        </div>
      </Card>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Appearance
// ---------------------------------------------------------------------------

function ThemeCard() {
  const { theme, setTheme } = useTheme()

  return (
    <Card>
      <CardHeader title="نمایش" subtitle="روشن یا تاریک بودن برنامه" />

      <div className="mt-4 grid grid-cols-2 gap-1 rounded-control bg-surface-muted p-1">
        {(['light', 'dark'] as const).map((option) => {
          const active = theme === option
          const Icon = option === 'light' ? Sun : Moon
          return (
            <button
              key={option}
              type="button"
              onClick={() => setTheme(option)}
              aria-pressed={active}
              className={[
                'flex h-10 items-center justify-center gap-2 rounded-control text-[13px] font-medium transition-colors',
                active ? 'bg-surface text-ink shadow-card' : 'text-ink-soft hover:text-ink',
              ].join(' ')}
            >
              <Icon className="size-4" aria-hidden="true" />
              {option === 'light' ? 'روشن' : 'تاریک'}
            </button>
          )
        })}
      </div>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Accounts
// ---------------------------------------------------------------------------

function AccountsSection() {
  const { data, isPending } = useAccounts()
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [editing, setEditing] = useState<Account | null>(null)

  const accounts = data?.results ?? []

  return (
    <div className="space-y-4">
      <Card padded={false}>
        <div className="flex items-center justify-between gap-3 border-b border-border px-4 py-3.5 sm:px-5">
          <div>
            <h2 className="text-[15px] font-semibold text-ink">حساب‌های مالی</h2>
            <p className="mt-0.5 text-xs text-ink-faint">
              موجودی هر حساب از تراکنش‌های ثبت‌شده محاسبه می‌شود
            </p>
          </div>
          <Button
            size="sm"
            onClick={() => {
              setEditing(null)
              setIsFormOpen(true)
            }}
            leadingIcon={<Plus className="size-4" aria-hidden="true" />}
            className="shrink-0"
          >
            افزودن
          </Button>
        </div>

        {isPending ? (
          <div className="space-y-2 p-4">
            {[0, 1].map((index) => (
              <div key={index} className="skeleton h-14 rounded-card" />
            ))}
          </div>
        ) : accounts.length === 0 ? (
          <p className="px-4 py-10 text-center text-[13px] text-ink-faint">
            هنوز حساب مالی‌ای ثبت نشده است.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {accounts.map((account) => (
              <li key={account.id}>
                <button
                  type="button"
                  onClick={() => {
                    setEditing(account)
                    setIsFormOpen(true)
                  }}
                  className="flex w-full items-center gap-3 px-4 py-3.5 text-start transition-colors hover:bg-surface-muted/60 sm:px-5"
                >
                  <span
                    className="flex size-10 shrink-0 items-center justify-center rounded-control"
                    style={{ backgroundColor: `${account.color}1a`, color: account.color }}
                  >
                    <UserIcon className="size-4.5" aria-hidden="true" />
                  </span>

                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-[13.5px] font-medium text-ink">
                        {account.name}
                      </span>
                      <Badge variant="neutral" size="sm">
                        {account.account_type_label}
                      </Badge>
                    </div>
                    {account.institution ? (
                      <p className="mt-0.5 truncate text-[11px] text-ink-faint">
                        {account.institution}
                      </p>
                    ) : null}
                  </div>

                  <span className="ltr-nums shrink-0 text-[13.5px] font-semibold text-ink">
                    {account.current_balance_display}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <AccountForm
        open={isFormOpen}
        account={editing}
        onClose={() => {
          setIsFormOpen(false)
          setEditing(null)
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Security
// ---------------------------------------------------------------------------

function SecuritySection() {
  const [feedback, setFeedback] = useState<{ tone: 'ok' | 'error'; text: string } | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    setError,
    formState: { errors, isSubmitting },
  } = useForm<PasswordValues>({
    resolver: zodResolver(passwordSchema),
    defaultValues: { current_password: '', new_password: '', new_password_confirm: '' },
  })

  const submit = handleSubmit(async (values) => {
    setFeedback(null)
    try {
      await authApi.changePassword({
        current_password: values.current_password,
        new_password: values.new_password,
        new_password_confirm: values.new_password_confirm,
      })
      reset()
      setFeedback({ tone: 'ok', text: 'رمز عبور با موفقیت تغییر کرد.' })
    } catch (error) {
      const fields = fieldErrors(error)
      let matched = false
      for (const [field, message] of Object.entries(fields)) {
        if (field in passwordSchema.shape || field === 'new_password_confirm') {
          setError(field as keyof PasswordValues, { message })
          matched = true
        }
      }
      setFeedback(
        matched
          ? null
          : { tone: 'error', text: errorMessage(error, 'تغییر رمز عبور انجام نشد.') },
      )
    }
  })

  return (
    <Card>
      <CardHeader
        title="تغییر رمز عبور"
        subtitle="برای امنیت بیشتر، رمز عبور خود را به‌صورت دوره‌ای تغییر دهید"
      />

      <form onSubmit={submit} noValidate className="mt-4 space-y-4">
        <Input
          label="رمز عبور فعلی"
          type="password"
          dir="ltr"
          autoComplete="current-password"
          error={errors.current_password?.message}
          {...register('current_password')}
        />

        <Input
          label="رمز عبور جدید"
          type="password"
          dir="ltr"
          autoComplete="new-password"
          placeholder={`حداقل ${MIN_PASSWORD} کاراکتر`}
          error={errors.new_password?.message}
          {...register('new_password')}
        />

        <Input
          label="تکرار رمز عبور جدید"
          type="password"
          dir="ltr"
          autoComplete="new-password"
          error={errors.new_password_confirm?.message}
          {...register('new_password_confirm')}
        />

        {feedback ? (
          <p
            role="status"
            className={[
              'rounded-control px-3 py-2 text-xs',
              feedback.tone === 'ok'
                ? 'bg-positive-50 text-positive-700'
                : 'bg-critical-50 text-critical-700',
            ].join(' ')}
          >
            {feedback.text}
          </p>
        ) : null}

        <Button type="submit" isLoading={isSubmitting}>
          تغییر رمز عبور
        </Button>
      </form>
    </Card>
  )
}
