import { useEffect, useMemo } from "react";

import { useAuth } from "../context/AuthContext";

const STORE_KEY = "automation_tenant_id";

export default function TenantSelect() {
  const { memberships } = useAuth();
  const tenantId = localStorage.getItem(STORE_KEY);

  useEffect(() => {
    if (memberships.length > 0 && !localStorage.getItem(STORE_KEY)) {
      localStorage.setItem(STORE_KEY, memberships[0].tenant_id);
    }
  }, [memberships]);

  const selectedExists = useMemo(
    () => memberships.some((m) => m.tenant_id === tenantId),
    [memberships, tenantId]
  );

  if (memberships.length === 0) {
    return null;
  }

  return (
    <select
      aria-label="Active tenant"
      value={selectedExists && tenantId ? tenantId : memberships[0].tenant_id}
      onChange={(event) => {
        localStorage.setItem(STORE_KEY, event.target.value);
        window.location.reload();
      }}
    >
      {memberships.map((membership) => (
        <option key={membership.id} value={membership.tenant_id}>
          {membership.tenant.name} ({membership.role_name})
        </option>
      ))}
    </select>
  );
}