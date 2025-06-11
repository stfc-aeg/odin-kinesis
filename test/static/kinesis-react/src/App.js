import './App.css';

import 'odin-react/dist/index.css'
import 'bootstrap/dist/css/bootstrap.min.css';

import React from "react";
import { OdinApp } from 'odin-react';

import Motor from './Motor'

function App(props) {

  // axios.defaults.baseURL = process.env.REACT_APP_ENDPOINT_URL;

  return (
    <OdinApp title="Motor Controls" navLinks={["Motors"]} icon_src='../odin.png'>
      <Motor></Motor>
    </OdinApp>
  );
}

export default App;