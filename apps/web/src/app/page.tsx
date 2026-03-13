/**
 * HomePage — Redirects to /dashboard.
 * Day 15: Dashboard UI.
 *
 * Protocols: None
 * SOLID: SRP — routing only
 */
import { redirect } from "next/navigation";

export default function HomePage() {
  redirect("/dashboard");
}
