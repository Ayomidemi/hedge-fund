export default function InvestMarketsPage() {
  return (
    <div className="mx-auto grid max-w-3xl gap-4 sm:grid-cols-2">
      <MarketCard title="United States" items={["S&P 500", "Nasdaq", "Dow", "Treasury yields"]} />
      <MarketCard title="Nigeria" items={["NGX ASI", "Banking", "Consumer", "Oil & Gas"]} />
    </div>
  );
}

function MarketCard({ title, items }: { title: string; items: string[] }) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-lg font-semibold">{title}</h2>
      <ul className="mt-3 space-y-2 text-sm text-zinc-600 dark:text-zinc-400">
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}
