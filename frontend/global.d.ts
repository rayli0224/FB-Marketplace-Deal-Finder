/// <reference types="react" />
/// <reference types="react-dom" />

// Fallback JSX namespace if @types/react isn't available
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
