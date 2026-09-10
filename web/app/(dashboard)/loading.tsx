export default function DashboardLoading() {
  return (
    <div className="animate-fade-in p-6 space-y-6 max-w-7xl mx-auto">
      {/* Top Header Skeleton */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-gray-100">
        <div className="space-y-2">
          <div className="h-7 w-56 bg-gray-200/80 rounded-md animate-pulse" />
          <div className="h-4 w-96 bg-gray-100 rounded-md animate-pulse" />
        </div>
        <div className="flex items-center gap-2">
          <div className="h-9 w-28 bg-gray-100 rounded-lg animate-pulse" />
          <div className="h-9 w-32 bg-gray-200/80 rounded-lg animate-pulse" />
        </div>
      </div>

      {/* KPI Cards Skeleton Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <div
            key={i}
            className="p-4 rounded-xl border border-gray-100 bg-white/60 shadow-xs space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="h-3.5 w-24 bg-gray-200/80 rounded animate-pulse" />
              <div className="w-6 h-6 rounded-lg bg-gray-100 animate-pulse" />
            </div>
            <div className="h-7 w-20 bg-gray-200 rounded animate-pulse" />
            <div className="h-3 w-32 bg-gray-100 rounded animate-pulse" />
          </div>
        ))}
      </div>

      {/* Content Area Skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 rounded-xl border border-gray-100 bg-white/80 p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <div className="h-5 w-40 bg-gray-200/80 rounded animate-pulse" />
            <div className="h-4 w-20 bg-gray-100 rounded animate-pulse" />
          </div>
          <div className="h-64 w-full bg-gray-50/80 rounded-lg animate-pulse" />
        </div>

        <div className="rounded-xl border border-gray-100 bg-white/80 p-5 space-y-4 shadow-xs">
          <div className="h-5 w-36 bg-gray-200/80 rounded animate-pulse" />
          <div className="space-y-2.5">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="h-10 w-full bg-gray-50 rounded-md animate-pulse" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
