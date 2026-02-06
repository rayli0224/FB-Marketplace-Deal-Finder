/// <reference types="react" />

declare module 'react/jsx-runtime' {
  export function jsx(
    type: any,
    props: any,
    key?: string | number
  ): any;
  export function jsxs(
    type: any,
    props: any,
    key?: string | number
  ): any;
  export function Fragment(props: { children?: any }): any;
}

// Ensure JSX namespace is available when React types aren't found
declare namespace JSX {
  interface IntrinsicElements {
    [elemName: string]: any;
  }
  interface Element {
    type: any;
    props: any;
    key: any;
  }
  interface ElementClass {
    render(): any;
  }
  interface ElementAttributesProperty {
    props: {};
  }
  interface ElementChildrenAttribute {
    children: {};
  }
}
