import { AlertTriangle, RefreshCw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  /** Changing this value (e.g. the current route) clears a previous error. */
  resetKey?: string;
}

interface State {
  error: Error | null;
}

/**
 * Without a boundary, React 18 unmounts the whole app when any component throws
 * while rendering, which leaves an empty page. This keeps the sidebar and header
 * usable and shows what went wrong instead.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Page failed to render:", error, info.componentStack);
  }

  componentDidUpdate(prev: Props) {
    if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null });
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" className="mx-auto max-w-xl rounded-2xl border border-red-200 bg-white p-6 text-center shadow-card">
        <span className="mx-auto mb-3 inline-flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-700">
          <AlertTriangle size={22} />
        </span>
        <p className="font-semibold text-forest-950">This page could not be displayed</p>
        <p className="mt-1 break-words text-sm text-slate-600" data-testid="render-error">
          {this.state.error.message}
        </p>
        <button
          onClick={() => this.setState({ error: null })}
          className="mt-4 inline-flex items-center gap-2 rounded-xl bg-forest-800 px-4 py-2.5 text-sm font-semibold text-white hover:bg-forest-700"
        >
          <RefreshCw size={16} /> Try again
        </button>
      </div>
    );
  }
}
