"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { cancelInvestOrder } from "@/lib/api";

export function InvestOrderActions({
  orderId,
  status,
}: {
  orderId: string;
  status: string;
}) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const canCancel = !["FILLED", "CANCELLED", "REJECTED"].includes(status);

  async function handleCancel() {
    setPending(true);
    try {
      await cancelInvestOrder(orderId);
      toast.success("Order cancelled.");
      router.refresh();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Order could not be cancelled.");
    } finally {
      setPending(false);
    }
  }

  if (!canCancel) {
    return null;
  }

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => void handleCancel()}
      className={buttonSecondaryClassName}
    >
      {pending ? "Cancelling..." : "Cancel order"}
    </button>
  );
}
