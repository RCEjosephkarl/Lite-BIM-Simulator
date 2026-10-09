/** A request keeps the home/revision it started with, independent of the UI. */
export interface RequestScope { projectId: string; revision: number | null; epoch: number }
export class StaleResponseError extends Error {
  constructor() { super("This response belongs to an earlier home or revision."); this.name = "StaleResponseError"; }
}
export class RequestState {
  private current: RequestScope;
  private operation: string | null = null;
  private listeners = new Set<(operation: string | null) => void>();
  constructor(projectId: string) { this.current = { projectId, revision: null, epoch: 0 }; }
  capture(): RequestScope { return { ...this.current }; }
  setProject(projectId: string, revision: number | null = null): void {
    const previous = this.current;
    this.current = { projectId, revision, epoch: previous.epoch + (projectId === previous.projectId ? 0 : 1) };
  }
  assertCurrent(scope: RequestScope, responseRevision?: number): void {
    const current = this.current;
    if (scope.epoch !== current.epoch || scope.projectId !== current.projectId
      || (responseRevision === undefined && scope.revision !== current.revision)
      || (responseRevision !== undefined && current.revision !== null && responseRevision < current.revision))
      throw new StaleResponseError();
  }
  busy(): boolean { return this.operation !== null; }
  begin(operation: string): () => void {
    if (this.operation) throw new Error("Another operation is running. Wait for it to finish, then retry.");
    this.operation = operation;
    this.emit();
    let released = false;
    return () => {
      if (released) return;
      released = true;
      this.operation = null;
      this.emit();
    };
  }
  subscribe(listener: (operation: string | null) => void): void {
    this.listeners.add(listener); listener(this.operation);
  }
  private emit(): void { this.listeners.forEach(listener => listener(this.operation)); }
}
