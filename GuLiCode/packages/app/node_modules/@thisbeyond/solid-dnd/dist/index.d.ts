import { ParentComponent, Setter, Component, JSX } from 'solid-js';
import { Store } from 'solid-js/store';
import { JSX as JSX$1 } from 'solid-js/jsx-runtime';

type CollisionDetector = (draggable: Draggable$1, droppables: Droppable$1[], context: {
    activeDroppableId: Id | null;
}) => Droppable$1 | null;
declare const closestCenter: CollisionDetector;
declare const closestCorners: CollisionDetector;
declare const mostIntersecting: CollisionDetector;

interface Point {
    x: number;
    y: number;
}
interface Transform {
    x: number;
    y: number;
}
declare class Layout {
    x: number;
    y: number;
    width: number;
    height: number;
    constructor(rect: {
        x: number;
        y: number;
        width: number;
        height: number;
    });
    get rect(): {
        x: number;
        y: number;
        width: number;
        height: number;
    };
    get left(): number;
    get top(): number;
    get right(): number;
    get bottom(): number;
    get center(): Point;
    get corners(): {
        topLeft: Point;
        topRight: Point;
        bottomRight: Point;
        bottomLeft: Point;
    };
}

type Id = string | number;
interface Coordinates {
    x: number;
    y: number;
}
type SensorActivator<K extends keyof HTMLElementEventMap> = (event: HTMLElementEventMap[K], draggableId: Id) => void;
interface Sensor {
    id: Id;
    activators: {
        [K in keyof HTMLElementEventMap]?: SensorActivator<K>;
    };
    coordinates: {
        origin: Coordinates;
        current: Coordinates;
        get delta(): Coordinates;
    };
}
type TransformerCallback = (transform: Transform) => Transform;
interface Transformer {
    id: Id;
    order: number;
    callback: TransformerCallback;
}
interface Item {
    id: Id;
    node: HTMLElement;
    layout: Layout;
    data: Record<string, any>;
    transformers: Record<Id, Transformer>;
    get transform(): Transform;
    get transformed(): Layout;
    _pendingCleanup?: boolean;
}
interface Draggable$1 extends Item {
}
interface Droppable$1 extends Item {
}
interface Overlay extends Item {
}
type DragEvent = {
    draggable: Draggable$1;
    droppable?: Droppable$1 | null;
    overlay?: Overlay | null;
};
interface DragDropState {
    draggables: Record<Id, Draggable$1>;
    droppables: Record<Id, Droppable$1>;
    sensors: Record<Id, Sensor>;
    active: {
        draggableId: Id | null;
        draggable: Draggable$1 | null;
        droppableId: Id | null;
        droppable: Droppable$1 | null;
        sensorId: Id | null;
        sensor: Sensor | null;
        overlay: Overlay | null;
    };
}
interface DragDropActions {
    addTransformer(type: "draggables" | "droppables", id: Id, transformer: Transformer): void;
    removeTransformer(type: "draggables" | "droppables", id: Id, transformerId: Id): void;
    addDraggable(draggable: Omit<Draggable$1, "transform" | "transformed" | "transformers">): void;
    removeDraggable(id: Id): void;
    addDroppable(droppable: Omit<Droppable$1, "transform" | "transformed" | "transformers">): void;
    removeDroppable(id: Id): void;
    addSensor(sensor: Omit<Sensor, "coordinates">): void;
    removeSensor(id: Id): void;
    setOverlay(overlay: Pick<Overlay, "node" | "layout">): void;
    clearOverlay(): void;
    recomputeLayouts(): boolean;
    detectCollisions(): void;
    draggableActivators(draggableId: Id, asHandlers?: boolean): Listeners;
    sensorStart(id: Id, coordinates: Coordinates): void;
    sensorMove(coordinates: Coordinates): void;
    sensorEnd(): void;
    dragStart(draggableId: Id): void;
    dragEnd(): void;
    onDragStart(handler: DragEventHandler): void;
    onDragMove(handler: DragEventHandler): void;
    onDragOver(handler: DragEventHandler): void;
    onDragEnd(handler: DragEventHandler): void;
}
interface DragDropContextProps {
    onDragStart?: DragEventHandler;
    onDragMove?: DragEventHandler;
    onDragOver?: DragEventHandler;
    onDragEnd?: DragEventHandler;
    collisionDetector?: CollisionDetector;
}
type DragDropContext = [Store<DragDropState>, DragDropActions];
type Listeners = Record<string, (event: HTMLElementEventMap[keyof HTMLElementEventMap]) => void>;
type DragEventHandler = (event: DragEvent) => void;
declare const DragDropProvider: ParentComponent<DragDropContextProps>;
declare const useDragDropContext: () => DragDropContext | null;

declare const DragDropSensors: ParentComponent;

declare const createPointerSensor: (id?: Id) => void;

interface Draggable {
    (element: HTMLElement, accessor?: () => {
        skipTransform?: boolean;
    }): void;
    ref: Setter<HTMLElement | null>;
    get isActiveDraggable(): boolean;
    get dragActivators(): Listeners;
    get transform(): Transform;
}
declare const createDraggable: (id: Id, data?: Record<string, any>) => Draggable;

interface Droppable {
    (element: HTMLElement, accessor?: () => {
        skipTransform?: boolean;
    }): void;
    ref: Setter<HTMLElement | null>;
    get isActiveDroppable(): boolean;
    get transform(): Transform;
}
declare const createDroppable: (id: Id, data?: Record<string, any>) => Droppable;

interface DragOverlayProps {
    children: JSX.Element | ((activeDraggable: Draggable$1 | null) => JSX.Element);
    class?: string;
    style?: JSX.CSSProperties;
}
declare const DragOverlay: Component<DragOverlayProps>;

interface SortableContextState {
    initialIds: Array<Id>;
    sortedIds: Array<Id>;
}
interface SortableContextProps {
    ids: Array<Id>;
}
type SortableContext = [Store<SortableContextState>, {}];
declare const SortableProvider: ParentComponent<SortableContextProps>;
declare const useSortableContext: () => SortableContext | null;

type RefSetter<V> = (value: V) => void;

interface Sortable {
    (element: HTMLElement): void;
    ref: RefSetter<HTMLElement | null>;
    get transform(): Transform;
    get dragActivators(): Listeners;
    get isActiveDraggable(): boolean;
    get isActiveDroppable(): boolean;
}
declare const createSortable: (id: Id, data?: Record<string, any>) => Sortable;

declare const layoutStyle: (layout: Layout) => JSX$1.CSSProperties;
declare const transformStyle: (transform: Transform) => JSX$1.CSSProperties;
declare const maybeTransformStyle: (transform: Transform) => JSX$1.CSSProperties;

declare const DragDropDebugger: () => JSX.Element;

export { CollisionDetector, DragDropDebugger, DragDropProvider, DragDropSensors, DragEvent, DragEventHandler, DragOverlay, Draggable$1 as Draggable, Droppable$1 as Droppable, Id, SortableProvider, Transformer, closestCenter, closestCorners, createDraggable, createDroppable, createPointerSensor, createSortable, layoutStyle, maybeTransformStyle, mostIntersecting, transformStyle, useDragDropContext, useSortableContext };
