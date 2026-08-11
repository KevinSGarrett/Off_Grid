declare namespace JSX { interface IntrinsicElements { [elemName: string]: any; } }
declare module "react" {
  export const StrictMode: any;
  export interface FormEvent { preventDefault(): void; }
  export function useEffect(effect: () => void | (() => void), deps: readonly unknown[]): void;
  export function useMemo<T>(factory: () => T, deps: readonly unknown[]): T;
  export function useState<T>(initial: T | (() => T)): [T, (value: T | ((previous: T) => T)) => void];
}
declare module "react/jsx-runtime" { export const Fragment: any; export function jsx(type:any, props:any, key?:any):any; export function jsxs(type:any, props:any, key?:any):any; }
declare module "react-dom/client" { export function createRoot(container: Element | DocumentFragment): { render(node:any):void }; }
