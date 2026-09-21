import { Toaster as SonnerToaster } from 'sonner'

// App-wide toast host, dark themed to match the UI. Use `toast()` from 'sonner' to fire.
export function Toaster(props) {
  return (
    <SonnerToaster
      theme="dark"
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
