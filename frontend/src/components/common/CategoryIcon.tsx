import {
  Activity,
  Award,
  Baby,
  Bike,
  BookOpen,
  Briefcase,
  Building,
  Bus,
  Car,
  CarTaxiFront,
  CircleEllipsis,
  Cloud,
  Coffee,
  Coins,
  CreditCard,
  Droplet,
  Dumbbell,
  Film,
  Flame,
  Footprints,
  Fuel,
  Gamepad2,
  Gem,
  Gift,
  GraduationCap,
  HandCoins,
  HandHeart,
  HeartPulse,
  HelpCircle,
  Home,
  Hotel,
  Languages,
  Landmark,
  Luggage,
  MapPin,
  Monitor,
  MoreHorizontal,
  Music,
  Palette,
  PawPrint,
  Percent,
  Phone,
  PiggyBank,
  Pill,
  Pizza,
  Plane,
  Receipt,
  Repeat,
  Scissors,
  Shield,
  Shirt,
  ShoppingBag,
  ShoppingBasket,
  ShoppingCart,
  Sofa,
  Sparkles,
  Star,
  Stethoscope,
  Tag,
  Ticket,
  Train,
  TrendingUp,
  Users,
  Utensils,
  UtensilsCrossed,
  Wallet,
  Wifi,
  Wrench,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

/**
 * Lucide icon names the backend accepts for a category, mapped to the actual
 * components.
 *
 * The list mirrors `CATEGORY_ICON_CHOICES` on the server. Importing each icon
 * explicitly (rather than the whole Lucide namespace) keeps the bundle small —
 * a dynamic import would pull in every icon in the library.
 *
 * The product spec forbids emoji as UI icons, so this map is the only source
 * of category iconography.
 */
export const CATEGORY_ICONS: Record<string, LucideIcon> = {
  // Food
  utensils: Utensils,
  'utensils-crossed': UtensilsCrossed,
  coffee: Coffee,
  pizza: Pizza,
  'shopping-basket': ShoppingBasket,
  // Transport
  car: Car,
  bus: Bus,
  plane: Plane,
  train: Train,
  bike: Bike,
  fuel: Fuel,
  taxi: CarTaxiFront,
  // Shopping
  'shopping-bag': ShoppingBag,
  'shopping-cart': ShoppingCart,
  shirt: Shirt,
  footprints: Footprints,
  gem: Gem,
  // Home
  home: Home,
  building: Building,
  sofa: Sofa,
  wrench: Wrench,
  zap: Zap,
  droplet: Droplet,
  flame: Flame,
  wifi: Wifi,
  phone: Phone,
  receipt: Receipt,
  // Health
  'heart-pulse': HeartPulse,
  pill: Pill,
  stethoscope: Stethoscope,
  dumbbell: Dumbbell,
  activity: Activity,
  // Leisure
  'gamepad-2': Gamepad2,
  film: Film,
  music: Music,
  ticket: Ticket,
  palette: Palette,
  // Learning
  'book-open': BookOpen,
  'graduation-cap': GraduationCap,
  languages: Languages,
  monitor: Monitor,
  // Travel
  'palm-tree': MapPin,
  hotel: Hotel,
  luggage: Luggage,
  'map-pin': MapPin,
  // Subscriptions & services
  repeat: Repeat,
  cloud: Cloud,
  shield: Shield,
  landmark: Landmark,
  'credit-card': CreditCard,
  // Family & personal
  users: Users,
  baby: Baby,
  scissors: Scissors,
  sparkles: Sparkles,
  'paw-print': PawPrint,
  gift: Gift,
  'hand-heart': HandHeart,
  // Income
  wallet: Wallet,
  briefcase: Briefcase,
  'trending-up': TrendingUp,
  'piggy-bank': PiggyBank,
  coins: Coins,
  percent: Percent,
  award: Award,
  'hand-coins': HandCoins,
  // Generic
  tag: Tag,
  'circle-ellipsis': CircleEllipsis,
  'more-horizontal': MoreHorizontal,
  star: Star,
  'help-circle': HelpCircle,
}

export interface CategoryIconProps {
  /** A name from `CATEGORY_ICON_CHOICES`, e.g. "utensils". */
  name: string | null | undefined
  /** The category's own colour, applied to the glyph. */
  color?: string | null
  /** The category's colour at low alpha, used as the well background. */
  size?: 'sm' | 'md' | 'lg'
  /** A tinted circle behind the glyph rather than a bare icon. */
  filled?: boolean
  className?: string
}

const SIZES = {
  sm: { box: 'size-8 rounded-control', icon: 'size-4' },
  md: { box: 'size-10 rounded-control', icon: 'size-5' },
  lg: { box: 'size-12 rounded-card', icon: 'size-6' },
} as const

/** Converts `#4f46e5` to `rgba(79, 70, 229, 0.12)` for the tinted well. */
function withAlpha(hex: string | null | undefined, alpha: number): string {
  if (!hex) return 'rgba(91, 98, 112, 0.10)'
  const clean = hex.replace('#', '')
  const full =
    clean.length === 3
      ? clean
          .split('')
          .map((c) => c + c)
          .join('')
      : clean
  const value = Number.parseInt(full, 16)
  if (!Number.isFinite(value)) return 'rgba(91, 98, 112, 0.10)'
  const r = (value >> 16) & 255
  const g = (value >> 8) & 255
  const b = value & 255
  return `rgba(${r}, ${g}, ${b}, ${alpha})`
}

/**
 * Renders a category's Lucide glyph on a tinted disc.
 *
 * Colour is decoration here, not information — the category name is always
 * rendered next to the icon by the calling component.
 */
export function CategoryIcon({
  name,
  color,
  size = 'md',
  filled = true,
  className = '',
}: CategoryIconProps) {
  const Icon = CATEGORY_ICONS[name ?? ''] ?? Tag
  const dimensions = SIZES[size]

  if (!filled) {
    return (
      <Icon
        className={[dimensions.icon, className].filter(Boolean).join(' ')}
        style={{ color: color ?? undefined }}
        aria-hidden="true"
      />
    )
  }

  return (
    <span
      className={[
        'inline-flex shrink-0 items-center justify-center',
        dimensions.box,
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      style={{ backgroundColor: withAlpha(color, 0.12) }}
    >
      <Icon
        className={dimensions.icon}
        style={{ color: color ?? undefined }}
        aria-hidden="true"
      />
    </span>
  )
}

export { withAlpha as categoryTint }
