import { cva } from 'class-variance-authority'

export { default as Badge } from './Badge.vue'

export const badgeVariants = cva(
  'inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors',
  {
    variants: {
      variant: {
        default: 'border-transparent bg-primary text-primary-foreground',
        secondary: 'border-transparent bg-secondary text-secondary-foreground',
        destructive: 'border-transparent bg-destructive text-destructive-foreground',
        outline: 'text-foreground',
        success: 'border-transparent bg-[color:var(--color-success)]/15 text-[color:var(--color-success)]',
        warning: 'border-transparent bg-[color:var(--color-warning)]/15 text-[color:var(--color-warning)]',
      },
    },
    defaultVariants: { variant: 'default' },
  }
)
