/**
 * Module declaration shims for packages without bundled TypeScript types.
 * Day 15: Dashboard UI foundation.
 */

declare module "react-grid-layout" {
  import type { ReactNode, CSSProperties } from "react";

  export interface Layout {
    i: string;
    x: number;
    y: number;
    w: number;
    h: number;
    minW?: number;
    maxW?: number;
    minH?: number;
    maxH?: number;
    static?: boolean;
    isDraggable?: boolean;
    isResizable?: boolean;
    isBounded?: boolean;
  }

  export interface ReactGridLayoutProps {
    className?: string;
    style?: CSSProperties;
    width: number;
    autoSize?: boolean;
    cols?: number;
    draggableCancel?: string;
    draggableHandle?: string;
    verticalCompact?: boolean;
    compactType?: "vertical" | "horizontal" | null;
    layout?: Layout[];
    margin?: [number, number];
    containerPadding?: [number, number] | null;
    rowHeight?: number;
    maxRows?: number;
    isDraggable?: boolean;
    isResizable?: boolean;
    isBounded?: boolean;
    useCSSTransforms?: boolean;
    transformScale?: number;
    preventCollision?: boolean;
    isDroppable?: boolean;
    resizeHandles?: Array<"s" | "w" | "e" | "n" | "sw" | "cw" | "se" | "ne" | "nw">;
    onLayoutChange?: (layout: Layout[]) => void;
    onDragStart?: (layout: Layout[], oldItem: Layout, newItem: Layout, placeholder: Layout, event: MouseEvent, element: HTMLElement) => void;
    onDrag?: (layout: Layout[], oldItem: Layout, newItem: Layout, placeholder: Layout, event: MouseEvent, element: HTMLElement) => void;
    onDragStop?: (layout: Layout[], oldItem: Layout, newItem: Layout, placeholder: Layout, event: MouseEvent, element: HTMLElement) => void;
    onResizeStart?: (layout: Layout[], oldItem: Layout, newItem: Layout, placeholder: Layout, event: MouseEvent, element: HTMLElement) => void;
    onResize?: (layout: Layout[], oldItem: Layout, newItem: Layout, placeholder: Layout, event: MouseEvent, element: HTMLElement) => void;
    onResizeStop?: (layout: Layout[], oldItem: Layout, newItem: Layout, placeholder: Layout, event: MouseEvent, element: HTMLElement) => void;
    children?: ReactNode;
  }

  const GridLayout: React.ComponentType<ReactGridLayoutProps>;
  export default GridLayout;
}

declare module "react-resizable" {
  export {};
}

declare module "echarts-for-react" {
  import type { Component, CSSProperties } from "react";
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  type EChartsOption = Record<string, any>;

  export interface EChartsReactProps {
    option: EChartsOption;
    style?: CSSProperties;
    className?: string;
    theme?: string | Record<string, unknown>;
    notMerge?: boolean;
    lazyUpdate?: boolean;
    showLoading?: boolean;
    loadingOption?: Record<string, unknown>;
    onChartReady?: (chart: unknown) => void;
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onEvents?: Record<string, (params: any) => void>;
    opts?: Record<string, unknown>;
  }

  export default class ReactECharts extends Component<EChartsReactProps> {
    getEchartsInstance(): unknown;
  }
}
