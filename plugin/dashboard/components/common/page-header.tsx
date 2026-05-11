import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  className,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "border-b border-border px-6 py-5 flex flex-wrap items-start justify-between gap-4",
        className,
      )}
    >
      <div className="min-w-[min(18rem,100%)] flex-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description && (
          <p className="text-sm text-muted-foreground mt-0.5">{description}</p>
        )}
      </div>
      {actions && (
        <div className="flex max-w-full flex-wrap items-center justify-end gap-2">
          {actions}
        </div>
      )}
    </div>
  );
}
