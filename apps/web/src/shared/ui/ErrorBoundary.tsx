"use client";

import { Component, type ReactNode } from "react";

/** Render xatosi butun sahifani yiqitmasin: faqat shu qism o‘rniga `fallback`. */
export class ErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}
