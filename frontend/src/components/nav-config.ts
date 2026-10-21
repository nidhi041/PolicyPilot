export interface NavItem {
  label: string;
  href: string;
  icon: string;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Employee Chat", href: "/chat", icon: "💬" },
  { label: "Policy Management", href: "/policies", icon: "📄" },
  { label: "HR Analytics", href: "/analytics", icon: "📊" },
] as const;

export function getPageTitle(pathname: string): string {
  const item = NAV_ITEMS.find((nav) => pathname.startsWith(nav.href));
  return item ? item.label : "PolicyPilot Enterprise";
}
