// frontend/src/components/MetricsCard.tsx

interface ForecastMetrics {
  mae: number
  rmse: number
  mape: number
  coverage: number | null
  horizon_days: number
  interpretation: string
}

interface MetricsCardProps {
  forecastId: number
  metrics: ForecastMetrics | null
  isLoading: boolean
  error: string | null
}

export function MetricsCard({ metrics, isLoading, error }: MetricsCardProps) {
  if (isLoading) {
    return (
      <div className="animate-pulse rounded-xl border border-white/10 bg-white/5 p-6">
        <div className="mb-4 h-4 w-40 rounded bg-white/10" />
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="space-y-2">
              <div className="h-3 w-12 rounded bg-white/10" />
              <div className="h-6 w-16 rounded bg-white/10" />
            </div>
          ))}
        </div>
      </div>
    )
  }

  if (error || !metrics) {
    return (
      <div className="rounded-xl border border-yellow-500/20 bg-yellow-950/10 p-4 text-sm text-yellow-400/80">
        Model accuracy metrics are not yet available for this forecast.
      </div>
    )
  }

  const mapeColor =
    metrics.mape < 10
      ? 'text-emerald-400'
      : metrics.mape < 20
      ? 'text-yellow-400'
      : 'text-red-400'

  return (
    <div className="rounded-xl border border-white/10 bg-white/5 p-6">
      <div className="mb-4 flex items-center gap-2">
        <svg
          className="h-5 w-5 text-blue-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
          />
        </svg>
        <h3 className="font-semibold text-white">Model Accuracy Metrics</h3>
        <span className="ml-auto text-xs text-white/40">
          {metrics.horizon_days}-day horizon
        </span>
      </div>

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        <MetricItem label="MAE" value={metrics.mae.toFixed(2)} hint="Mean Absolute Error (lower is better)" />
        <MetricItem label="RMSE" value={metrics.rmse.toFixed(2)} hint="Root Mean Squared Error (lower is better)" />
        <MetricItem
          label="MAPE"
          value={`${metrics.mape.toFixed(1)}%`}
          hint="Mean Absolute % Error"
          valueClass={mapeColor}
        />
        <MetricItem
          label="Coverage"
          value={metrics.coverage != null ? `${metrics.coverage.toFixed(1)}%` : 'N/A'}
          hint="% of actuals within confidence interval"
        />
      </div>

      <p className={`mt-4 text-xs font-medium ${mapeColor}`}>
        {metrics.interpretation}
      </p>
    </div>
  )
}

function MetricItem({
  label,
  value,
  hint,
  valueClass = 'text-white',
}: {
  label: string
  value: string
  hint: string
  valueClass?: string
}) {
  return (
    <div title={hint} className="cursor-help">
      <p className="text-xs text-white/40">{label}</p>
      <p className={`text-xl font-bold ${valueClass}`}>{value}</p>
    </div>
  )
}