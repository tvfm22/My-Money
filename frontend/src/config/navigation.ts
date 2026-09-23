import {
  ArrowLeftRight,
  BarChart3,
  HandCoins,
  Home,
  Lightbulb,
  MessageSquareText,
  PieChart,
  Settings,
  Wallet,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

export interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  /** Shown in the bottom nav on phones (five fit comfortably). */
  inBottomNav: boolean
  /** Grouping heading in the desktop sidebar. */
  section: 'main' | 'analysis' | 'setup'
}

/**
 * The app's information architecture, in one place.
 *
 * Both the desktop sidebar and the mobile bottom navigation are generated from
 * this list, so a new section can never appear in one and be forgotten in the
 * other.
 */
export const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'خانه', icon: Home, inBottomNav: true, section: 'main' },
  {
    to: '/transactions',
    label: 'تراکنش‌ها',
    icon: ArrowLeftRight,
    inBottomNav: true,
    section: 'main',
  },
  { to: '/budgets', label: 'بودجه‌ها', icon: PieChart, inBottomNav: true, section: 'main' },
  { to: '/debts', label: 'بدهی‌ها', icon: HandCoins, inBottomNav: true, section: 'main' },
  { to: '/assets', label: 'دارایی‌ها', icon: Wallet, inBottomNav: true, section: 'main' },
  {
    to: '/sms',
    label: 'پیامک بانکی',
    icon: MessageSquareText,
    inBottomNav: false,
    section: 'main',
  },
  { to: '/reports', label: 'گزارش‌ها', icon: BarChart3, inBottomNav: false, section: 'analysis' },
  {
    to: '/insights',
    label: 'بینش مالی',
    icon: Lightbulb,
    inBottomNav: false,
    section: 'analysis',
  },
  { to: '/settings', label: 'تنظیمات', icon: Settings, inBottomNav: false, section: 'setup' },
]

export const NAV_SECTIONS: Array<{ key: NavItem['section']; label: string }> = [
  { key: 'main', label: 'مدیریت' },
  { key: 'analysis', label: 'تحلیل' },
  { key: 'setup', label: 'تنظیمات' },
]

export const MOBILE_NAV_ITEMS = NAV_ITEMS.filter((item) => item.inBottomNav)
