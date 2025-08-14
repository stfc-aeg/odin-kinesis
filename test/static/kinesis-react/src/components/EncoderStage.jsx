import React, {useState} from 'react';

import { TitleCard, ToggleSwitch, WithEndpoint } from 'odin-react';
import Col from 'react-bootstrap/Col';
import Row from 'react-bootstrap/Row';
import Button from 'react-bootstrap/esm/Button';

import InputGroup from 'react-bootstrap/InputGroup';
import Form from 'react-bootstrap/Form';
import Accordion from 'react-bootstrap/Accordion';

const EndPointFormControl = WithEndpoint(Form.Control);
const EndPointToggle = WithEndpoint(ToggleSwitch);
const EndPointButton = WithEndpoint(Button);

function EncoderStage(props){
  const {name, data, kinesisEndPoint, dataPath} = props;

  const [targetPosition, setTargetPosition] = useState(data.position.set_target_pos ?? '');
  const handleTargetChange = (event) => {
    setTargetPosition(event.target.value);
  };

  return (
    <TitleCard title={"Motor "+name}>
    <Row>
      <Col xs={3}>
        <Row>
          <Col>
            <label>Position (mm)</label>
          </Col>
        </Row>
        <Row>
          <InputGroup>
            <InputGroup.Text style={{width:100}}>Current: </InputGroup.Text>
              <InputGroup.Text>{data.position.current_pos}</InputGroup.Text>
          </InputGroup>
        </Row>
        <Row>
          <InputGroup>
            <InputGroup.Text style={{width:100}}>Target:</InputGroup.Text>
              <Form.Control
                type="number"
                value={targetPosition}
                event_type="enter"
                onChange={handleTargetChange}
                disabled={data.moving}
              >
              </Form.Control>
          </InputGroup>
        </Row>
        <Row>
          <EndPointButton
            endpoint={kinesisEndPoint}
            fullpath={dataPath+"/position/set_target_pos"}
            event_type="click"
            value={targetPosition}
          >
            Move to target
          </EndPointButton>
        </Row>
      </Col>
      <Col xs={4}>
        <Row className="mb-3">
          <Col>
            <EndPointButton
              endpoint={kinesisEndPoint}
              fullpath={dataPath + "/jog/step"}
              event_type="click"
              value={true}
            >
              Step forward
            </EndPointButton>
          </Col>
          <Col>
            <EndPointButton
              endpoint={kinesisEndPoint}
              fullpath={dataPath + "/jog/step"}
              event_type="click"
              value={false}
            >
              Step backward
            </EndPointButton>
          </Col>
        </Row>

        <Accordion>
          <Accordion.Item eventKey="0">
            <Accordion.Header>Jog/step settings</Accordion.Header>
            <Accordion.Body>
              <Row>
                <Col>
                  <Form.Check
                    type="checkbox"
                    label="Reverse forward/back"
                  />
                </Col>
              </Row>
              <InputGroup className="mt-2">
                <InputGroup.Text>Step</InputGroup.Text>
                <EndPointFormControl
                  endpoint={kinesisEndPoint}
                  fullpath={dataPath + "/jog/step_size"}
                  type="number"
                  event_type="enter"
                  value={data.jog.step_size}
                />
              </InputGroup>
              <InputGroup className="mt-2">
                <InputGroup.Text>Max vel.</InputGroup.Text>
                <EndPointFormControl
                  endpoint={kinesisEndPoint}
                  fullpath={dataPath + "/jog/max_vel"}
                  type="number"
                  event_type="enter"
                  value={data.jog.max_vel}
                />
              </InputGroup>
              <InputGroup className="mt-2">
                <InputGroup.Text>Accel.</InputGroup.Text>
                <EndPointFormControl
                  endpoint={kinesisEndPoint}
                  fullpath={dataPath + "/jog/accel"}
                  type="number"
                  event_type="enter"
                  value={data.jog.accel}
                />
              </InputGroup>
            </Accordion.Body>
          </Accordion.Item>
        </Accordion>
      </Col>
      <Col xs={3}>
        <Row>
          <InputGroup className="mt-2">
            <InputGroup.Text>Upper limit (mm)</InputGroup.Text>
            <EndPointFormControl
              endpoint={kinesisEndPoint}
              fullpath={dataPath + "/limits/upper_limit"}
              type="number"
              event_type="enter"
              value={data.limits.upper_limit}
            />
          </InputGroup>
          <InputGroup className="mt-2">
            <InputGroup.Text>Lower limit (mm)</InputGroup.Text>
            <EndPointFormControl
              endpoint={kinesisEndPoint}
              fullpath={dataPath + "/limits/lower_limit"}
              type="number"
              event_type="enter"
              value={data.limits.lower_limit}
            />
          </InputGroup>
        </Row>
      </Col>
      <Col xs={2}>
        <Row>
          <EndPointButton
            endpoint={kinesisEndPoint}
            fullpath={dataPath+"/position/home"}
            event_type="click"
            value={true}
          >
             Home
          </EndPointButton>
        </Row>
        <Row className="mt-3">
          <EndPointButton
            endpoint={kinesisEndPoint}
            fullpath={dataPath+"/position/stop"}
            event_type="click"
            variant="danger"
            value={true}
          >
            Stop movement
          </EndPointButton>
        </Row>
      </Col>
    </Row>
    </TitleCard>
  );
}

export default EncoderStage;
