export interface NavItem {
  label: string;
  href: string;
  icon: string;
  hrOnly?: boolean;
}

export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Employee Chat", href: "/chat", icon: "💬" },
  { label: "Policy Management", href: "/policies", icon: "📄", hrOnly: true },
  { label: "HR Analytics", href: "/analytics", icon: "📊", hrOnly: true },
] as const;

export function canAccessRoute(pathname: string, isAuth: boolean, isHrAdmin: boolean): boolean {
  if (!isAuth) return false;
  if (!isHrAdmin && (pathname.startsWith("/policies") || pathname.startsWith("/analytics"))) {
    return false;
  }
  return true;
}

export function getVisibleNavItems(isHrAdmin: boolean): readonly NavItem[] {
  return NAV_ITEMS.filter((item) => !item.hrOnly || isHrAdmin);
}

export function getPageTitle(pathname: string): string {
  const item = NAV_ITEMS.find((nav) => pathname.startsWith(nav.href));
  return item ? item.label : "PolicyPilot Enterprise";
}
