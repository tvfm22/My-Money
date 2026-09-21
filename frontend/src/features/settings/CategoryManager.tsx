import { useMemo, useState } from 'react'
import { ChevronDown, Pencil, Plus, Trash2 } from 'lucide-react'
import { Card } from '../../components/ui/Card'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Badge } from '../../components/ui/Badge'
import { useToast } from '../../components/ui/Toast'
import { ResponsiveDialog } from '../../components/ui/ResponsiveDialog'
import { CategoryIcon, CATEGORY_ICONS, categoryTint } from '../../components/common/CategoryIcon'
import {
  useCategoryMeta,
  useCategoryTree,
  useCreateCategory,
  useDeleteCategory,
  useUpdateCategory,
} from '../../hooks/queries'
import { errorMessage, fieldErrors } from '../../services/client'
import type { Category, CategoryKind } from '../../types'

/**
 * Category management.
 *
 * Rendered as an expandable parent/child tree because that is how the data
 * actually behaves: a parent like «حمل‌ونقل» owns «تاکسی» and «سوخت», and a
 * flat list of fifty-six rows hides that.
 */
export function CategoryManager() {
  const [kind, setKind] = useState<CategoryKind>('expense')
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const [editing, setEditing] = useState<Category | null>(null)
  const [isFormOpen, setIsFormOpen] = useState(false)
  const [parentForNew, setParentForNew] = useState<Category | null>(null)
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null)

  const { data: tree, isPending } = useCategoryTree()
  const deleteCategory = useDeleteCategory()
  const { showToast } = useToast()

  const roots = useMemo(
    () => (tree ?? []).filter((category) => category.kind === kind),
    [tree, kind],
  )

  const toggle = (id: number) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const openCreate = (parent: Category | null) => {
    setEditing(null)
    setParentForNew(parent)
    setIsFormOpen(true)
  }

  return (
    <div className="space-y-4">
      <Card padded={false}>
        <div className="flex flex-col gap-3 border-b border-border px-4 py-3.5 sm:flex-row sm:items-center sm:justify-between sm:px-5">
          <div>
            <h2 className="text-[15px] font-semibold text-ink">دسته‌بندی‌ها</h2>
            <p className="mt-0.5 text-xs text-ink-faint">
              دسته‌بندی‌ها و زیردسته‌های خود را مدیریت کنید
            </p>
          </div>

          <div className="flex items-center gap-2">
            <div className="flex gap-1 rounded-control bg-surface-muted p-1">
              {(['expense', 'income'] as const).map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setKind(option)}
                  aria-pressed={kind === option}
                  className={[
                    'h-8 rounded-control px-3 text-[12px] font-medium transition-colors',
                    kind === option ? 'bg-surface text-ink shadow-card' : 'text-ink-soft',
                  ].join(' ')}
                >
                  {option === 'expense' ? 'هزینه' : 'درآمد'}
                </button>
              ))}
            </div>

            <Button
              size="sm"
              onClick={() => openCreate(null)}
              leadingIcon={<Plus className="size-4" aria-hidden="true" />}
            >
              افزودن
            </Button>
          </div>
        </div>

        {isPending ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2].map((index) => (
              <div key={index} className="skeleton h-12 rounded-card" />
            ))}
          </div>
        ) : roots.length === 0 ? (
          <p className="px-4 py-10 text-center text-[13px] text-ink-faint">
            دسته‌بندی‌ای در این بخش وجود ندارد.
          </p>
        ) : (
          <ul className="divide-y divide-border">
            {roots.map((parent) => {
              const children = parent.children ?? []
              const isOpen = expanded.has(parent.id)

              return (
                <li key={parent.id}>
                  {/* Parent row */}
                  <div className="flex items-center gap-2.5 px-4 py-3 sm:px-5">
                    <button
                      type="button"
                      onClick={() => toggle(parent.id)}
                      disabled={children.length === 0}
                      aria-expanded={isOpen}
                      aria-label={children.length > 0 ? `نمایش زیردسته‌های ${parent.name}` : undefined}
                      className={[
                        'flex size-9 shrink-0 items-center justify-center rounded-control text-ink-faint transition-colors',
                        children.length > 0 ? 'hover:bg-surface-muted active:bg-surface-muted' : 'opacity-0 pointer-events-none',
                      ].join(' ')}
                    >
                      <ChevronDown
                        className={['size-3.5 transition-transform', isOpen ? 'rotate-180' : ''].join(' ')}
                        aria-hidden="true"
                      />
                    </button>

                    <CategoryIcon name={parent.icon} color={parent.color} size="md" />

                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="truncate text-[13.5px] font-medium text-ink">
                          {parent.name}
                        </span>
                        {parent.is_default ? (
                          <Badge variant="neutral" size="sm">
                            پیش‌فرض
                          </Badge>
                        ) : null}
                      </div>
                      {children.length > 0 ? (
                        <p className="mt-0.5 text-[11px] text-ink-faint">
                          <span className="ltr-nums">{children.length}</span> زیردسته
                        </p>
                      ) : null}
                    </div>

                    <RowActions
                      onAddChild={() => openCreate(parent)}
                      onEdit={() => {
                        setEditing(parent)
                        setParentForNew(null)
                        setIsFormOpen(true)
                      }}
                      onDelete={() => setConfirmingDelete(parent.id)}
                      isConfirming={confirmingDelete === parent.id}
                      isDeleting={deleteCategory.isPending}
                      onCancelDelete={() => setConfirmingDelete(null)}
                      onConfirmDelete={() => {
                        deleteCategory.mutate(parent.id, {
                          onSuccess: () => showToast({ message: 'دسته‌بندی حذف شد.' }),
                        })
                        setConfirmingDelete(null)
                      }}
                    />
                  </div>

                  {/* Children */}
                  {isOpen && children.length > 0 ? (
                    <ul className="bg-surface-muted/50">
                      {children.map((child) => (
                        <li
                          key={child.id}
                          className="flex items-center gap-2.5 border-t border-border/60 px-4 py-2.5 ps-14 sm:px-5 sm:ps-16"
                        >
                          <CategoryIcon name={child.icon} color={child.color} size="sm" />

                          <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink-soft">
                            {child.name}
                          </span>

                          <RowActions
                            onEdit={() => {
                              setEditing(child)
                              setParentForNew(null)
                              setIsFormOpen(true)
                            }}
                            onDelete={() => setConfirmingDelete(child.id)}
                            isConfirming={confirmingDelete === child.id}
                            isDeleting={deleteCategory.isPending}
                            onCancelDelete={() => setConfirmingDelete(null)}
                            onConfirmDelete={() => {
                              deleteCategory.mutate(child.id, {
                                onSuccess: () => showToast({ message: 'زیردسته حذف شد.' }),
                              })
                              setConfirmingDelete(null)
                            }}
                          />
                        </li>
                      ))}
                    </ul>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
      </Card>

      <CategoryForm
        open={isFormOpen}
        category={editing}
        parent={parentForNew}
        defaultKind={kind}
        onClose={() => {
          setIsFormOpen(false)
          setEditing(null)
          setParentForNew(null)
        }}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------

function RowActions({
  onAddChild,
  onEdit,
  onDelete,
  isConfirming,
  isDeleting,
  onCancelDelete,
  onConfirmDelete,
}: {
  onAddChild?: () => void
  onEdit: () => void
  onDelete: () => void
  isConfirming: boolean
  isDeleting: boolean
  onCancelDelete: () => void
  onConfirmDelete: () => void
}) {
  if (isConfirming) {
    return (
      <div className="flex shrink-0 items-center gap-1">
        <Button variant="danger" size="sm" onClick={onConfirmDelete} isLoading={isDeleting}>
          حذف
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancelDelete}>
          انصراف
        </Button>
      </div>
    )
  }

  return (
    <div className="flex shrink-0 items-center gap-0.5">
      {onAddChild ? (
        <button
          type="button"
          onClick={onAddChild}
          aria-label="افزودن زیردسته"
          className="flex size-9 items-center justify-center rounded-control text-ink-faint transition-colors hover:bg-surface-muted hover:text-ink active:bg-surface-muted"
        >
          <Plus className="size-3.5" aria-hidden="true" />
        </button>
      ) : null}

      <button
        type="button"
        onClick={onEdit}
        aria-label="ویرایش"
        className="flex size-9 items-center justify-center rounded-control text-ink-faint transition-colors hover:bg-surface-muted hover:text-ink active:bg-surface-muted"
      >
        <Pencil className="size-3.5" aria-hidden="true" />
      </button>

      <button
        type="button"
        onClick={onDelete}
        aria-label="حذف"
        className="flex size-9 items-center justify-center rounded-control text-ink-faint transition-colors hover:bg-critical-50 hover:text-critical-600 active:bg-critical-50"
      >
        <Trash2 className="size-3.5" aria-hidden="true" />
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------

const COLOUR_SWATCHES = [
  '#3566e8',
  '#12a150',
  '#e08c00',
  '#dc2b2b',
  '#5b5bd6',
  '#0ea5b7',
  '#8b5cf6',
  '#ec4899',
  '#64748b',
]

function CategoryForm({
  open,
  category,
  parent,
  defaultKind,
  onClose,
}: {
  open: boolean
  category: Category | null
  parent: Category | null
  defaultKind: CategoryKind
  onClose: () => void
}) {
  const isEditing = category !== null
  const { data: meta } = useCategoryMeta()
  const createCategory = useCreateCategory()
  const updateCategory = useUpdateCategory()
  const { showToast } = useToast()

  const [name, setName] = useState('')
  const [kind, setKind] = useState<CategoryKind>(defaultKind)
  const [icon, setIcon] = useState('tag')
  const [color, setColor] = useState(COLOUR_SWATCHES[0])
  const [error, setError] = useState<string | null>(null)

  // Reset the draft whenever the dialog opens or its subject changes.
  const subjectKey = `${open}-${category?.id ?? 'new'}-${parent?.id ?? 'root'}`
  const [lastKey, setLastKey] = useState(subjectKey)

  if (lastKey !== subjectKey) {
    setLastKey(subjectKey)
    setError(null)
    if (category) {
      setName(category.name)
      setKind(category.kind)
      setIcon(category.icon)
      setColor(category.color)
    } else {
      setName('')
      setKind(parent?.kind ?? defaultKind)
      setIcon('tag')
      setColor(COLOUR_SWATCHES[0])
    }
  }

  const icons = (meta?.icons ?? Object.keys(CATEGORY_ICONS)).slice(0, 40)

  const submit = async () => {
    if (!name.trim()) {
      setError('نام دسته‌بندی را وارد کنید.')
      return
    }

    setError(null)

    const payload: Partial<Category> = {
      name: name.trim(),
      kind,
      icon,
      color,
    }

    if (!isEditing && parent) {
      payload.parent = parent.id
    }

    try {
      if (isEditing && category) {
        await updateCategory.mutateAsync({ id: category.id, ...payload })
        showToast({ message: 'تغییرات دسته‌بندی ذخیره شد.' })
      } else {
        await createCategory.mutateAsync(payload)
        showToast({ message: 'دسته‌بندی جدید اضافه شد.' })
      }
      onClose()
    } catch (err) {
      const fields = fieldErrors(err)
      const first = Object.values(fields)[0]
      setError(first ?? errorMessage(err, 'ذخیره دسته‌بندی انجام نشد. دوباره تلاش کنید.'))
    }
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      title={
        isEditing
          ? 'ویرایش دسته‌بندی'
          : parent
            ? `افزودن زیردسته به ${parent.name}`
            : 'افزودن دسته‌بندی'
      }
      footer={
        <div className="flex gap-2">
          <Button variant="ghost" onClick={onClose} className="flex-1">
            انصراف
          </Button>
          <Button
            onClick={submit}
            isLoading={createCategory.isPending || updateCategory.isPending}
            className="flex-[2]"
          >
            {isEditing ? 'ذخیره تغییرات' : 'افزودن'}
          </Button>
        </div>
      }
    >
      <div className="space-y-4">
        <Input
          label="نام دسته‌بندی"
          placeholder="مثلاً رستوران و کافه"
          value={name}
          onChange={(event) => {
            setName(event.target.value)
            setError(null)
          }}
        />

        {!parent ? (
          <fieldset>
            <legend className="mb-2 text-[13px] font-medium text-ink-soft">نوع</legend>
            <div className="grid grid-cols-2 gap-2">
              {(['expense', 'income'] as const).map((option) => (
                <label
                  key={option}
                  className={[
                    'flex h-11 cursor-pointer items-center justify-center rounded-control border text-[13px] font-medium transition-colors',
                    kind === option
                      ? option === 'expense'
                        ? 'border-critical-500 bg-critical-50 text-critical-700'
                        : 'border-positive-500 bg-positive-50 text-positive-700'
                      : 'border-border-strong bg-surface text-ink-soft hover:bg-surface-muted',
                  ].join(' ')}
                >
                  <input
                    type="radio"
                    className="sr-only"
                    checked={kind === option}
                    onChange={() => setKind(option)}
                  />
                  {option === 'expense' ? 'هزینه' : 'درآمد'}
                </label>
              ))}
            </div>
          </fieldset>
        ) : null}

        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink-soft">آیکون</legend>
          <div className="grid max-h-52 grid-cols-7 gap-1.5 overflow-y-auto rounded-control border border-border p-2 sm:grid-cols-8">
            {icons.map((iconName) => (
              <button
                key={iconName}
                type="button"
                onClick={() => setIcon(iconName)}
                aria-pressed={icon === iconName}
                aria-label={iconName}
                className={[
                  'flex aspect-square items-center justify-center rounded-control transition-colors',
                  icon === iconName
                    ? 'bg-brand-50 ring-2 ring-brand-500'
                    : 'hover:bg-surface-muted',
                ].join(' ')}
              >
                <CategoryIcon name={iconName} color={color} size="sm" filled={false} />
              </button>
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2 text-[13px] font-medium text-ink-soft">رنگ</legend>
          <div className="flex flex-wrap gap-2">
            {COLOUR_SWATCHES.map((swatch) => (
              <button
                key={swatch}
                type="button"
                onClick={() => setColor(swatch)}
                aria-pressed={color === swatch}
                aria-label={`رنگ ${swatch}`}
                className={[
                  'flex size-9 items-center justify-center rounded-control border-2 transition-colors',
                  color === swatch ? 'border-ink' : 'border-transparent',
                ].join(' ')}
              >
                <span
                  className="size-6 rounded-pill"
                  style={{ backgroundColor: swatch }}
                />
              </button>
            ))}
          </div>
        </fieldset>

        {/* Live preview so the choice is concrete before saving. */}
        <div className="flex items-center gap-3 rounded-card border border-border p-3">
          <span
            className="flex size-10 items-center justify-center rounded-control"
            style={{ backgroundColor: categoryTint(color, 0.12) }}
          >
            <CategoryIcon name={icon} color={color} size="md" filled={false} />
          </span>
          <div>
            <p className="text-[13.5px] font-medium text-ink">{name || 'نام دسته‌بندی'}</p>
            <p className="mt-0.5 text-[11px] text-ink-faint">
              {kind === 'expense' ? 'هزینه' : 'درآمد'}
              {parent ? ` • زیردسته ${parent.name}` : ''}
            </p>
          </div>
        </div>

        {error ? (
          <p role="alert" className="rounded-control bg-critical-50 px-3 py-2 text-xs text-critical-700">
            {error}
          </p>
        ) : null}
      </div>
    </ResponsiveDialog>
  )
}
