import { render, RenderOptions } from "@testing-library/react";
import { ReactNode } from "react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Custom render function that includes BrowserRouter and QueryClientProvider
 * for components that use React Router hooks (useNavigate, Link, etc.)
 */
export function renderWithRouter(
  ui: ReactNode,
  options?: Omit<RenderOptions, "wrapper">
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
      },
    },
  });

  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          {children}
        </BrowserRouter>
      </QueryClientProvider>
    );
  }

  return render(ui, { wrapper: Wrapper, ...options });
}

/**
 * Re-export everything from testing-library react
 */
/* eslint-disable react-refresh/only-export-components */
export * from "@testing-library/react";
