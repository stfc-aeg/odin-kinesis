import './App.css';

import 'odin-react/dist/index.css'
import 'bootstrap/dist/css/bootstrap.min.css';

import Container from 'react-bootstrap/Container';
import Row from 'react-bootstrap/Row';

import React from "react";
import { useAdapterEndpoint } from 'odin-react';

import KdcController from './components/KdcController';
import EncoderStage from './components/EncoderStage';

import KimController from './components/KimController';
import PiezoStage from './components/PiezoStage';

function Motor(props)
{
    const endpoint_url = process.env.REACT_APP_ENDPOINT_URL;

    const kinesisEndPoint = useAdapterEndpoint('kinesis', endpoint_url, 500);
    const controllers = kinesisEndPoint?.data?.controllers;
  
    const componentMap = {
      'kim101': KimController,
      'kdc101': KdcController
    };

    return (
        <Container>
        {!controllers ? (
        <Row> No controllers found</Row>
        ) : (
        Object.entries(controllers).map(([controllerName, controllerData]) => {
            const ControllerComponent = componentMap[controllerData.type.toLowerCase()];
            if (ControllerComponent) {
            return (
                <ControllerComponent
                key={controllerName}
                name={controllerName}
                motors={controllerData.motors}
                kinesisEndPoint={kinesisEndPoint}
                />
            )
            }
            else {
            return (
                <Row>Unknown controller type: {controllerData.type}</Row>
            )
            }
        }
        ))}
        </Container>
    );
}

export default Motor;
