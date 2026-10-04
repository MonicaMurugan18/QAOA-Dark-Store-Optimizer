export default function EmptyState({ icon: Icon, title, message, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {Icon ? (
        <span className="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-ink-100 text-ink-400">
          <Icon size={20} />
        </span>
      ) : null}
      <h3 className="text-[14px] font-semibold text-ink-800">{title}</h3>
      {message ? (
        <p className="mt-1.5 max-w-md text-[13px] leading-relaxed text-ink-500">
          {message}
        </p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  );
}
