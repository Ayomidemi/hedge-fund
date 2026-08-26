import { redirect } from "next/navigation";

export default function AttributionPage() {
  redirect("/reports?view=attribution");
}
