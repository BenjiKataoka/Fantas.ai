import { Toaster as SonnerToaster } from 'sonner'
import { useTheme } from '@/lib/theme'

// App-wide toast host, follows the light/dark theme. Use `toast()` from 'sonner' to fire.
export function Toaster(props) {
  const theme = useTheme()
  return (
    <SonnerToaster
      theme={theme}
      richColors
      position="bottom-right"
      toastOptions={{
        classNames: {
          toast: 'bg-surface border border-line text-content',
        },
      }}
      {...props}
    />
  )
}
